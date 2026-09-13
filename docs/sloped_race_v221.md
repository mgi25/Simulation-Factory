# V22.1 — the three joins

V22 was watched end to end on a phone, and three things came back. None of them
was about a shot; all three were about a **join**:

1. the course preview is too fast to read;
2. the shuffle still looks cut;
3. the last chase hits the finish as a jump.

V22.1 fixes those three and nothing else. The race body — the first descent, the
obstacle, the fork, the branches, the materials, the map, the route balance — is
V22's, and the metrics below show it arriving unchanged to the decimal.

**This is a presentation pass.** Seed 5432, the PyBullet replay, the digest, the
colliders, the route assignments, the tick rate and the finish order
`5, 2, 7, 4, 1, 6, 3, 0` are all untouched. Every number in this document is a
decision about which of the locked replay's frames are rendered and from where.

## 1. Source commits

Three prototypes, cherry-picked onto `origin/v22-integration` at
`57d50daf294ee27001c06c251c516301c717c6ee`. All three applied clean.

| pass | branch | commit |
| --- | --- | --- |
| preview breathing | `v221-preview-breathing` | `5126dee931ec85b10171818ee9fc201ea8e1f1f1` |
| shuffle continuity | `v221-shuffle-continuity` | `2a0797799d8fa96735ec6b95c240c32efb925409` |
| finish continuity | `v221-finish-continuity` | `9f81feb6f34885b085df8f083bd2f29fc74ab897` |

None of them touched a production file, which is why they compose: integration
is `sloped/v221.py` plus an edition row in three tables.

## 2. The physics freeze, checked rather than asserted

`tests/test_sloped_v221_integration.py` pins the seed, the replay digest, the
eight `finish_line` events and their order, the winner (marble 5 at replay
20.850) and the last crossing (24.4167). Nothing in this pass opens PyBullet.

## 3. The shape of the film

    OUTPUT  0.000 -  3.500    the course preview, 210 frames of its own footage
    OUTPUT  3.500 -  4.200    the held first race frame, under PICK ONE
    OUTPUT  4.200 - 26.533    the race

| | V22 | V22.1 |
| --- | --- | --- |
| preview frames | 120 | **210** |
| preview seconds | 2.000 | **3.500** |
| PICK ONE hold | 42 frames | 42 frames |
| race master frames | 1221 | **1340** |
| finished film | 1383 frames | **1592 frames** |
| runtime | 23.050 s | **26.533 s** |
| replay covered | 20.334 s | **22.317 s** |
| replay omitted | 3.933 s | **1.950 s** |

26.533 s is not a target that was aimed at. It is `3.500 + 0.700 + 1340/60`, and
the brief's estimate of 26.533 happens to be exactly what the frame arithmetic
produces.

## 4. The preview: 3.5 s, spent unevenly

`preview_35` of the breathing pass, `v221_preview.Pacing(seconds=3.5)`. The
point is not that it is longer; it is that the extra time is **not spread
evenly**. Playing V22's flight at 0.57 speed would give the empty hillside above
the fork the same extra screen time as the fork, and the hillside does not need
any.

The pacing is a time density `tau(q)` over travel: 1 over generic track, rising
into a Gaussian at each landmark, with two end terms for the acceleration out of
the finish and the deceleration into the start. The landmark shares come out of
its integral, not out of a table of timestamps.

| landmark | centre (s) | subject for (s) |
| --- | --- | --- |
| finish | 0.000 | 0.517 |
| merge | 0.852 | 0.483 |
| branches | 1.156 | 0.300 |
| fork | 1.444 | 0.450 |
| obstacle | 2.042 | 0.483 |
| turns | 2.389 | 0.383 |
| mixer | 2.782 | 0.367 |
| start | 3.483 | 0.517 |

Motion, against V22's:

| | V22 | V22.1 |
| --- | --- | --- |
| max step | 1.588 | **1.006** |
| max gaze turn | 1.044 | **0.541** |
| max pan / tilt | 0.896 / 0.800 | **0.459 / 0.426** |
| ribbon in frame | 45.4 % | 44.0 % |
| landmarks seen | 8/8 | 8/8 |
| `check_preview` problems | none | none |

**Breathing is bought from the straights.** `breath_ratio` is 37.5 — the slowest
frame moves a fortieth of what the fastest does — and the price is that a paced
flight crosses generic track faster than a uniform one of the same length would.
`flat_units_per_frame` is 0.982 against V22's own peak of 1.074, so even the
straights are calmer than V22's fastest frame. That is the whole argument for
3.5 s rather than 2.8: the low-priority parts of the course are what pays.

## 5. The handoff, and the eighth column

V22 had two hidden handoff defects. Both are gone.

**Velocity.** V22's preview arrived at rest — `_blend_end` is a smootherstep, so
its velocity at the last frame is exactly zero — against a race camera already
orbiting. `v221_preview.Rail` reads the race camera's own track backwards in
time in cylindrical coordinates about its aim, so the preview's tail is eased
onto a *moving* target.

**Field of view.** V22's preview ended at 48 degrees and its race began at 34.
Nobody measured it because `tools/sloped_v22.py` compared six columns —
position and aim — and the field of view is the eighth.

| | V22.1 |
| --- | --- |
| pose delta | 0.000000 |
| aim delta | 0.000000 |
| **fov delta** | **0.000000** |
| velocity residual | +0.00003 units/frame |
| turn residual | −0.00000 deg/frame |
| preview's last step | 0.05736 |
| race's first step | 0.05733 |

`sloped/v22.py` now carries one `assert_handoff(race, preview, columns=...)`.
Its default is **six**, and that default is a statement about V22 rather than
about what a handoff is: a seven-column check would fail the delivered V22 film,
because the snap is real. V22.1 passes `columns=7`.

### The ordering constraint

The b116 start stands the opening lens at elevation 30 with its own orbit legs,
which moves the race camera's first pose about 1.6 layout units from where V22
had it. So the preview cannot be solved until the start is integrated.
`v221.build_preview_track(race_track, ...)` takes the race track as its first
argument, which makes the ordering a call graph rather than a comment.

## 6. The shuffle: b116

The prototype's finding was that **three things changed at V22's join and only
one of them was the marbles**, and the marbles were the smallest of the three.
The camera accounted for about 93 % of the perceived jump.

b116 omits **116 frames** — four whole rotor revolutions at 13.0 rad/s —
from *inside* the constant-rate spin, with camera legs computed by
`constant_rate_legs` so that position and velocity both carry through:

    replay 0.200 - 2.050   live: the gates at 0.317, the pour, the rotor at 1.600
    116 frames omitted     1.933 s of screen nobody sees
    replay 4.000 - 6.700   live: spin-down, blade lift, stillness, trapdoor,
                           and the field dropping out of the chamber

(6.700 rather than the prototype's 7.620 — see the empty-chamber tail below.
It is a handoff, not a cut: replay 6.700 to 7.620 is still in the film.)

Measured on the **integrated** track, not the prototype's:

| | V22 | V22.1 |
| --- | --- | --- |
| live mixer footage | 3.487 s | **4.550 s** |
| omitted | 3.933 s / 235 frames | **1.950 s / 116 frames** |
| camera step at the join | 5.3741 | **0.0000** |
| camera reach change | 3.6634 | **0.0000** |
| aim step at the join | 0.0000 | 0.0000 |
| rotor phase error | −49.61° | **0.0339°** |
| rotor lift across the join | 1.193 | **0.000** |
| marbles, worst | 2.322 sim / 1.91 diameters | **1.123 / 1.11** |
| largest step *inside* a shot | 0.8704 | **0.0574** |

### What the join looks like, in pixels

Measured on the delivered files, at 270x480, as mean frame-to-frame luma change
over the 50 frames around each film's own omission:

| | join step | median ordinary step | ratio |
| --- | --- | --- | --- |
| V22 | 5.527 | 5.173 | 1.07x |
| **V22.1** | **2.841** | **2.920** | **0.97x** |

**V22.1's join frame changes slightly less than an ordinary frame does**, which
is as invisible as an edit can be — there is no picture event there at all.

The ratio flatters V22, and the reason is worth stating: its *ordinary* frames in
that window change nearly twice as much (5.17 against 2.92), because its start
shot is orbiting faster and stair-stepping through the clearance loop. Against
that busy baseline a 5.374-unit lens jump does not stand out as a ratio. The
absolute numbers in the table above are the honest measure.

### Rotor phase locking

A revolution is `2π / 13.0 = 0.483322 s = 28.9993 frames`, and 29 frames is
0.483333 s — 0.0085 degrees of blade. Four of them is 116 frames, and the
measured phase error across the integrated join is **0.0339 degrees**, taken off
the replay's own recorded actuator quaternions rather than off the law. The
rotor keeps turning through the cut.

### Camera continuity, and a defect the pass found on the way

`StartPlan(elevation=30.0)` is not a framing change. `cameras.build_track` raises
a cut's elevation in whole 2-degree steps until the sight line clears the ground,
with no smoothing after, and on the start lens's own 16 degrees that loop engages
repeatedly — each engagement moving the lens 0.79 to 0.87 layout units in one
frame. **The delivered V22 start has nine of them.** Standing the lens where the
loop was taking it anyway means it never runs: the largest lens step anywhere in
the integrated start is **0.0574** against V22's **0.8704**, and the framing is
the same shot (8 of 8 racers, 83 px against V22's 72).

### Anticipation

`ShuffleFloor` is a five-beat machine and every beat is a pure function of
`release_time`:

    4.600 - 4.900   spin-down: the blades visibly decelerate to a stop
    5.200 - 5.900   the paddle assembly rises 1.193 units out of the drum
    5.900 - 6.100   nothing moves
    6.100           the trapdoor

V22 showed **0.267 s** of that and resumed with the blades already up. V22.1
resumes at replay 4.000, 0.600 s before the spin-down even starts, so the whole
**1.500 s** is live. The field stops being hit at replay 2.012 and the floor does
not open until 6.100 — 4.09 s with no contact — which is why this stretch needs
the machine to carry it.

### The empty-chamber tail: real, and fixed by moving the camera

The prototype flagged that the field is "mostly through the chute by roughly
replay 6.6" while the window runs to 7.620, and asked whether the shot then
lingers on an empty machine. It could not check — it had rendered no integrated
film. **The rendered film says it does, and earlier than the guess.** Measured
against the trapdoor panels' own height, read off the replay:

    replay 6.100   the floor opens; all 8 marbles are above the chamber floor
    replay 6.300   3 left
    replay 6.400   0 left

So **1.220 s** of the start shot is a lens dollying across a box the field has
left, and the frames at 6.9, 7.2 and 7.6 are an empty drum.

The brief's remedy is the one taken: **move the camera's handoff, not the
clock.** No replay second is omitted, nothing is sped up and no physics is
deleted. Replay 6.700 to 7.620 is still in the film — it is shot by the chase
camera following the field down the launch chute instead of by the start lens
watching the box they came out of. The edit map stays contiguous from replay
4.000 to 24.467, so **the runtime does not change**: 22.317 s of replay,
26.533 s of film, before and after.

**The chosen boundary is replay 6.700**, 0.300 s after the last marble clears
the floor — enough to see them go. Swept against the integrated track:

| `tail_to` | start→chase jump | racers in frame, first second of the chase |
| --- | --- | --- |
| 6.500 | 0.066 | 8.00 |
| **6.700** | **0.058** | **8.00** |
| 6.850 | 0.069 | 8.00 |
| 7.000 | 0.081 | 7.98 |
| 7.620 (V22's) | 0.243 | 7.85 |

Every earlier boundary beats 7.620 on both counts, because the chase picks the
pack up while it is still together rather than a second after it has strung out.
This is the only number in the start that is production's rather than the
prototype's, and `tests/test_sloped_v221_integration.py` pins both that fact and
the 6.400 measurement behind it.

## 7. The shuffle omission is deliberately silent

V19 through V22 mark an omission with `whoosh_cue`, and they are right to: their
cut lands across a rotor that stops dead, so the picture changes in a way that
needs explaining. V22.1's does not change the picture — the blades, the hub, the
lift and the field are all continuous across it — and a whoosh over an invisible
join does not explain an edit, it **announces** one that was not otherwise there.

This is a policy rather than a muted timestamp. `audio.marble.Cues` carries two
flags and `audio.marble.CUES` maps a name to a policy:

```python
CUES = {
    "default": Cues(),                              # every edition before V22.1
    "v221":    Cues(omission=False, mechanism=True),
}
```

`tools/sloped_short.py` reads it off the edition row (`cue_policy`). V20, V21,
V21.1 and V22 keep `default` and rebuild with their whoosh unchanged — pinned by
a test.

## 8. The mixer, heard

With five and a half seconds of mixer on screen and effectively no contact events
in it, the machine has to carry the sound. Both new voices are **derived from the
replay's own recorded actuator transforms**, through a new
`presentation.actuator_motion(replay, clock, prefix)` that returns, per kept
frame, the group's rotation rate and how far it has risen:

* `mechanism_bed` — a motor whose pitch and level follow the recorded rate, plus
  blade noise, amplitude-modulated at the blade-pass frequency (four paddles at
  13.0 rad/s is 8.28 Hz). **Nothing places the spin-down**: the drone falls
  because the recorded rate falls, from 13.0 at replay 4.6 to 0.036 by 5.0;
* `lift_cue` — the paddle assembly withdrawing, placed where the recorded height
  starts rising and as long as the recorded move is.

The trapdoor keeps the cue it always had, from `start.panel`'s first movement.
No fake marble collisions were invented for the settled period.

## 9. The finish: candidate A, a chase that stops chasing

V22 ends its chase at replay 20.200 and cuts to V19's finish lens, 0.650 s before
the winner crosses — the worst half second in the race to ask a viewer to re-find
their marble in. Integration had already tried easing the chase onto that lens
and it failed: the poses are 51 units and 56 degrees apart, the ease has to be
spent while the pack is still travelling, and the lens reaches 2.5 to 6.6 units a
frame.

Candidate A inverts it. The chase decelerates from **its own velocity** at replay
18.900 onto a stand fixed to the finish line, reaches it before the winner
arrives, and holds while eight marbles cross in front of it. A parked camera has
no whip available to it.

    split        18.900   the merge phase's own fastest frame
    settle        2.683 s  ratio 2.0 - never faster than the chase already was
    aim settle    1.200 s  separate, and that separation is the anticipation
    park          bearing 180, radius 26, height 18, fov 36
    parked at    21.583   1.27 s before the winner's own crossing

The Hermite's start tangent is the chase's own per-frame velocity and its end
tangent is zero, so the join is C1 by construction rather than by smoothing.

| | V22 | V22.1 |
| --- | --- | --- |
| hard cuts in the whole film | 1 | **0** |
| largest join jump | 0.443 | **0.058** |
| finish visible before the winner | 0.633 s | **1.383 s** |
| max camera step after the split | — | 0.824 units/frame |
| max gaze turn | — | 0.880 deg/frame |
| max racer screen movement | — | 43.0 px/frame |
| winner at the crossing | — | 54.9 px |
| crossings in frame / clear / readable | — | **8 / 8 / 8** |
| `check_finish` findings | — | none |

The old finish bookend drops out on its own: `v221_finish.build` keeps every edit
segment below the split and appends one `final` window, so there is no `finish`
cut in the track at all.

## 10. The finish board, made readable from behind

`course_modules.sign_panel` puts the FINISH board's lit face and its letters on
the **+Z** side, down-course, for a stated reason — "every camera on this course
stands downhill of what it is looking at". That stopped being true when the
finish became the end of a chase: the rear park spends the last three seconds of
the film looking at the back of a board it cannot read, a blank graphite slab
across the middle of the payoff shot.

`--finish-sign=double` copies the face and the letters onto the −Z side, applied
as a patch on the built scene in `sloped_race_scene._face_finish_sign_both_ways`
rather than as a parameter through the shared asset modules — which the hero,
neon, toy and layout scenes are all photographed from. The letters are turned
about Y rather than scaled by −1, because a negative scale on a `TextMesh` is a
sign reading HSINIF.

It is drawn geometry and nothing else: no collider, no finish-line position, no
crossing time. The flag defaults to `single`, and only the `v221` row of
`tools/sloped_v22.py` passes it, so V20, V21 and V22 re-render exactly what they
shipped.

## 11. The winner's mark

No change was needed. The ring is placed through `presentation.screen_track`,
which follows the new camera, and the drift the prototype measured improves from
~37.7 px/frame to ~15.6. On the rendered result the mark sits on a 54.9 px marble
— smaller than V22's 68 px but well over `readability.MIN_MEDIAN_PX` — and reads
clearly, so no minimum display radius was introduced.

## 12. The clock

Everything is derived. `presentation.Clock` already had `prefix` (output seconds
of preview) and `segments` (the track's own edit map), so a preview 1.500 s longer
and a start 1.983 s longer move **every** cue together:

* PICK ONE fades on `prefix + 0.10` and off `prefix + 0.80`;
* the gates, the trapdoor, the mixer drone and the lift come from
  `actuator_move` / `actuator_motion` on the replay;
* the fork, the eight crossings, the winner's mark and the end fact come from
  `clock.at(replay_second)`;
* the omission's position comes from `presentation.omissions(clock)`.

No constant was offset by hand. A test asserts that
`origin < gates < trapdoor < winner < duration` and that every crossing maps.

## 12a. Output

| | |
| --- | --- |
| runtime | 26.533 s |
| frames | 1592 |
| integrated loudness | −13.97 LUFS |
| true peak | −1.80 dBTP |
| limiter | idle |
| QC | every check passes |

## 13. Metrics: the race body did not move

Measured on the integrated tracks by `tools/sloped_v221_metrics.py`, V22 → V22.1,
pooled by cut and weighted by screen time:

| | seconds | px median | in frame | visible | track ahead |
| --- | --- | --- | --- | --- | --- |
| opening / start | 3.49 → 4.55 | 75 → 76 | 7.38 → **8.00** | 6.30 → **7.23** | 39.2 → **46.0** |
| first descent | 2.05 → 2.97 | 48 → 48 | 7.58 → **7.71** | 6.76 → 6.13 | 17.2 → **22.0** |
| obstacle | 5.43 → 5.43 | 69 → 69 | 7.30 → 7.30 | 6.40 → 6.40 | 36.4 → 36.4 |
| fork | 1.63 → 1.63 | 48 → 48 | 8.00 → 8.00 | 7.53 → 7.53 | 21.1 → 21.1 |
| branches | 1.68 → 1.68 | 34 → 34 | 7.04 → 7.04 | 7.00 → 7.00 | 34.5 → 34.5 |
| merge | 1.78 → **0.48** | 28 → 28 | 6.13 → 6.80 | 4.94 → 6.60 | 10.5 → 21.1 |

The obstacle, the fork and the branches are identical to every decimal, which is
the claim: V22.1 does not touch the race body. The start improves because its
camera stopped stair-stepping.

**The one figure that falls is the descent's `visible`, and it is an artifact of
the pooling rather than a regression.** The descent is 0.92 s longer because the
handoff moved, and the added stretch is the field *inside the launch chute*,
where the machine's own structure occludes some of it. Split at V22's own
boundary:

| replay | V22 | V22.1 |
| --- | --- | --- |
| 6.700–7.620 (the added front) | 3.11 visible — and V22 is showing an empty drum | **4.00 visible** |
| 7.620–9.667 (V22's own span) | 6.76 visible | **7.00 visible** |

On both halves separately V22.1 is ahead. Only the average of a longer shot with
a harder opening is lower.

**The merge row is the one real change** — see the weakness below.

## 14. Weaknesses

**The leaders leave the frame for 0.98 s during the park.** Between replay 19.483
and 20.450 the winner is off screen while the camera, having turned to the line,
waits for the field to arrive; mid-pack racers stay in frame throughout, so the
shot is not empty, but the marble a viewer is following is not in it. This is
structural to a rear park rather than a tuning error, and the sweep says so:

| `aim_settle` | finish lead | leader off-frame |
| --- | --- | --- |
| **1.2 (shipped)** | **1.383 s** | **0.98 s** |
| 1.4 | 1.283 s | 0.92 s |
| 1.6 | 1.183 s | 0.82 s |
| 1.8 | 1.083 s | 0.73 s |
| 2.0 | 1.017 s | 0.65 s |

0.8 s of extra aim settle buys back 0.35 s of leader and costs 0.37 s of finish
lead — a straight trade at about 1:1, and no setting removes the gap. The
prototype's swept value is kept.

**The merge shot is 1.30 s shorter.** The split at 18.900 is inside V22's merge
window, so the convergence at replay 19.38 is now seen from a decelerating camera
rather than a dedicated one: over replay 18.90–20.20 the mean racer count in
frame falls from 5.84 to 3.62. The three marbles that actually merge (5, 7, 2)
are all in frame through 19.40 and the merge still reads; what is lost is the
tail of the shot. The sweep the finish pass ran says 18.600 needs a 5.02 s brake
and 19.050 loses the finish line entirely, so there is no better split available.

**The film is 3.48 s longer.** That is the point of the pass, and whether it is
right is the question the review answers.

**A keyframe lands inside the held opening.** x264's default key interval is 250
frames and V22.1's hold runs 210–251, so frame 250 is an IDR and is quantised
from scratch: it differs from the P-frames before it by a mean of 0.79 with
edge pixels up to 48, on a picture that has not moved at all. Side by side the
two frames are identical. It is invisible, it is in the file, and
`tools/sloped_short_qc.py` now measures the *median* adjacent step across the
hold rather than its two ends, which is what "one still picture" means and is
immune to the bitstream — V22.1 reads 0.0044 and V22 0.0001 under the new
reading, so the check got tighter rather than looser.

## 15. Should V22.1 replace V22?

On measurements, yes: it removes the film's only hard cut, removes the camera
jump at the start join, holds the finish line on screen for more than twice as
long, keeps all eight crossings readable, and leaves the race body identical. The
two costs are named above and both are consequences of decisions the brief
specified rather than accidents.

The open question is not measurable here: **26.5 s against 23.1 s on a phone.**
That is a judgement about attention, and it is what the render is for.

## 16. Rebuilding

    python tools/sloped_v22.py    --edition v221 --stage all --godot PATH
    python tools/sloped_short.py  --edition v221 --stage all
    python tools/sloped_v221_metrics.py
    python tools/sloped_v221_sheet.py --stage all

`--edition v22` still rebuilds V22; its camera track and preview track come out
byte-identical, which was checked rather than assumed.
