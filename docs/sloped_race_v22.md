# V22 — cinematic race flow, in one film

Status: **integrated and rendered, awaiting review.** Three prototypes developed
on three branches off the same V21 commit, solved into one camera language, one
clock and one Short. No physics, no re-simulation, no course geometry, no seed
change. The replay is the same file it has been since V1.15 and the race is bit
for bit the one V20 and V21 shipped.

    output/sloped_race_v1/real_race_v22_master.mp4   1080x1920, 60 fps, 1383 frames
                                                     23.050 s, no overlays, no audio
    output/sloped_race_v1/real_race_v22_visual.mp4   the same picture with overlays
    output/sloped_race_v1/real_race_v22.mp4          the Short: AAC 48 kHz, 33.8 MiB

`real_race_v19.mp4`, `real_race_v20.mp4` and `real_race_v21.mp4` are untouched,
and `--edition v20`, `--edition v211` and `--edition v21` all still rebuild.

## 1. What V22 is for

V21 solved technical readability: it made the racers big enough and the frame
contrasty enough to follow. It did not change what the film is, which was a
highlight montage — eleven short spectator shots, two temporal omissions, and a
picture that stopped while two marbles were still racing.

V22 is about **flow**. One continuous camera language behind the pack, a course
preview so the viewer knows what is coming, the mixing put back, the obstacle put
back, and a finish that lets the race end.

    COURSE PREVIEW -> ARRIVE BEHIND START -> PICK ONE -> GATE + SHUFFLE ->
    TRAPDOOR -> CHASE DESCENT -> OBSTACLE (approach, interaction, escape) ->
    FORK -> BRANCHES -> MERGE -> FINAL CHASE -> CLEAR FINISH

## 2. Source commits

Three commits, each exactly one ahead of `main` at `9f4d175`, with disjoint file
sets. All three cherry-picked **clean, with no conflicts and no edits**; every
one of them was purely additive — twelve new files between them and not a single
line changed in any existing production file.

| pass | source commit | on this branch |
|---|---|---|
| V22 pacing | `63d75cb` | `591aade` |
| V22 course preview | `c5cdea1` | `e4d5e66` |
| V22 chase camera | `fb2a59e` | `69acd9c` |

    sloped/v22_timeline.py, tools/sloped_v22_pacing.py, tests/test_sloped_v22_pacing.py
    sloped/course_preview.py, tools/sloped_course_preview.py, tests/test_sloped_course_preview.py
    sloped/chase_camera.py, tools/sloped_chase_camera.py, tests/test_sloped_chase.py

plus the three documents. Because the three commits touched nothing that
existed, **all of the integration is new work** — which is the opposite of V21,
where the integration risk was three passes editing the same master.

## 3. Physics, replay and identity

Nothing on this branch is upstream of anything that decides the race.

* seed **5432**, 8 marbles, 2701 replay frames, 45.00 s;
* finish order **5, 2, 7, 4, 1, 6, 3, 0**, marble 5 winning by 0.283 s;
* crossings at replay 20.850, 21.133, 21.717, 22.633, 22.650, 23.500, 24.317,
  24.417 — unchanged, and now **all eight are in the film**;
* `tests/test_sloped_v22_integration.py` asserts the seed and the order off the
  replay rather than trusting them.

## 4. The clock, which is the actual integration

The three prototypes each have a clock and they are not the same clock. The
preview's camera timestamps are *output* times under an identity edit map; the
race runs on a replay/edit map; the pacing pass works in master frame numbers.
Merging the preview's edit array into the race's would have produced a film
whose soundtrack was two seconds out and whose overlays were on the wrong shots.

So `presentation.Clock` grew one field, `prefix`, and the model is explicit:

    OUTPUT 0.000 - 2.000      the course preview, its own 120 frames
    OUTPUT 2.000 - 2.700      the held first race frame, under PICK ONE
    OUTPUT 2.700 - 23.050     the race, through cameras.EDITS["v22"]

`hold` clones the master's first frame, so the picture during it *is* a replay
instant and `replay_at` says which. `prefix` is different footage, so
`replay_at` returns `None` there and `at()` never maps a replay second into it.
Everything downstream — audio placement, the whoosh, the winner ring, the end
card, QC — reads the clock and needed no second offset of its own.

**The one arithmetic trap, written down because it is easy to get wrong.** The
preview is 120 frames and its own report calls its duration **1.9833 s**, which
is the span from the first frame's centre to the last's. What it costs the
output clock is **120/60 = 2.000 s**. Using 1.9833 would put every cue in the
film one frame early. `v22.preview_prefix` takes frames over fps and a test pins
the distinction.

`prefix` defaults to 0.0, so every number `Clock` returns for V20, V21.1 and V21
is the number it returned before this branch existed — asserted, not assumed.

## 5. The preview, and where it hands over

The course-preview pass's reverse dolly, unchanged in concept: begin near the
finish, travel backwards up the course, arrive behind the start.

    120 frames, 60 fps, 2.000 s of screen (1.9833 s of frame centres)
    fov 48, 8 of 8 landmarks in frame, 45.4% of the course ribbon on average
    step max 1.588  across 0.390  turn max 1.044  pan 0.896  tilt 0.800
    check_preview: no problems

It shows, in order: finish, final section, merge, branches, fork, obstacle,
turns, mixer, start. Every one of the eight landmarks is in frame.

**The handoff is exact.** `Preview.end_pose` is given the chase camera's own
first `(position, aim)`, and the preview's last frame lands on it to
**0.000000 layout units**. There is no cut between the preview and the race —
the same lens keeps going, and the held frame that follows is a continuation of
the arrival rather than a new shot.

Two of the preview's numbers changed to buy that, and one of the race's did.

**`cameras.V22_START_ORBIT = (-36, 4)` — the live start shot spends the angle.**
The chase stands at `START_BEARING` 230, round behind the machine; the preview
arrives down the corridor's own axis. Those are **32 degrees apart in azimuth
about a subject 25 layout units away**, and something has to spend that angle.
Spent inside the preview's tail it is a 1.9 degrees-a-frame pan, nearly twice
what `course_preview` allows, and stretching the blend does not fix it: from a
0.32 window to a 0.85 one the peak pan only falls 2.17 to 1.20. Spent by the
start shot instead it is 40 degrees over 1.7 s — **0.39 degrees a frame** — and
it happens under the gates opening rather than under a still frame.

It is close to free, and that was swept rather than argued. From -6 to -42 the
start shot holds **8 racers of 8 at 72 px at every setting**, its own worst lens
step *falls* slightly (0.870 to 0.844 units a frame), and `check_chase` returns
no findings at any of them. What moves is the preview: one failing check becomes
none, and the ribbon in frame goes 32% to 45%.

**`Preview.ease` 0.65 -> 0.45 and `end_blend` 0.32 -> 0.72.** The authored 0.65
was chosen so the flight settles into the handoff — "reads as arriving rather
than as being cut away from". With an explicit `end_pose` that argument moves:
the blend is a smootherstep onto the target, so its velocity is already zero at
the last frame whatever the ease does, and a firm ease only piles the flight's
own motion into the middle of the shot where the blend is also working. At 0.65
the lens moves 1.71 units in a frame against the 1.60 a dolly may; at 0.45 it is
1.59 and the shot passes clean.

### A blend that was tried and is not here

Interpolating the handoff in the aim's polar frame — azimuth, elevation and
reach, so the lens swings *round* the machine at constant distance — looks like
the right curve and is worse. The arc is longer than the chord, the peak step
goes 1.36 to 1.82 units a frame, and the pan does not improve. Reverted.

## 6. Pacing: Candidate A, and the two restorations

The pacing pass's recommended timeline, adopted exactly. `cameras.EDITS["v22"]`
is V21.2's eleven lenses with **four window edges moved and nothing else
touched** — derived from `EDIT_V212` in code rather than retyped, so every lens,
bearing, side, dolly and orbit is still the one V21.2 measured.

    #  lens      replay from   replay to   seconds   what changed
    0  start        0.200000    1.900000     1.700   the dial: 2.300 -> 1.900
       -- omit 1.900000 -> 5.833333, 3.933 s, ONE whoosh --
    1  start        5.833333    7.620000     1.787   was a frame cut, now a window
    2  descent      7.620000    8.620000     1.000
    3  long         8.620000    9.800000     1.180
    4  hairpin      9.800000   10.800000     1.000
    5  straight    10.800000   12.000000     1.200
    6  obstacle    12.000000   15.350000     3.350   +0.850 RESTORED
    7  split       15.350000   17.670000     2.320
    8  branch      17.670000   19.070000     1.400
    9  merge       19.070000   20.200000     1.130
    10 finish      20.200000   24.467000     4.267   +0.867 RESTORED

    replay covered  20.3337 s        picture 1263 frames = 21.050 s
    + preview 120 frames             film    1383 frames = 23.050 s

**Mixing.** Candidate A stops the first window on the frame churn falls through
the floor: **1.583 s of live mixing against V21's 0.683**, and 13 of the drum's
15 contacts against 7. The viewer sees the gates open, the eight pour out, the
tumble, and a settled field — then one honest skip.

**The obstacle, which needed no special handling.** The chase covers replay
7.620 to 20.200 in one unbroken span, so the 0.850 s V19 cut at 14.500 is not a
window that had to be added — it is a window the chase never had. That is why
the film's *only* omission is the one in the start, and why there is exactly one
whoosh.

**The finish.** 7th and 8th cross at 24.317 and 24.417; V21 stopped at 23.600
with two marbles still running. V22 runs to 24.467 and every one of the eight
crossings is on screen and has a sound.

**V22 makes no frame cut at all.** V21.1 took 85 frames out of a finished file
because the mixing it wanted back was already rendered and the obstacle it
wanted back was not. V22 re-renders, so all three are window bounds and
`EDITIONS["v22"]["cuts"]` is empty.

## 7. The camera: eight shots, one language

    #  shot      out from    out to    replay from   replay to
    0  start       2.7000    4.4000       0.2000      1.9000    V21's lens, orbit -36
    1  start       4.4000    6.1867       5.8333      7.6200    V21's lens
    2  descent     6.1867    8.2333       7.6200      9.6667    chase
    3  obstacle    8.2333   13.6667       9.6667     15.1000    chase
    4  fork       13.6667   15.3000      15.1000     16.7333    chase
    5  branches   15.3000   16.9833      16.7333     18.4167    chase
    6  merge      16.9833   18.7667      18.4167     20.2000    chase
    7  finish     18.7667   23.0337      20.2000     24.4670    V19's lens

Eight shots against V21's eleven, and five of them are one continuous solve.
`chase_camera.check_chase` returns **no findings**.

**The film has one real cut.** Measured by `readability.continuity_report` as
how far a shared racer moves across a boundary, in frame diagonals:

    start -> start       0.009      (across the omission)
    start -> descent     0.243
    descent -> obstacle  0.000
    obstacle -> fork     0.000
    fork -> branches     0.000
    branches -> merge    0.000
    merge -> finish      0.443

The four interior chase boundaries are **exactly zero** — they are not cuts at
all, they are set-point changes inside one continuous camera. V21 had ten
boundaries, three of them over 0.25, and a worst of 0.605.

## 8. Phase by phase, V21 against V22

Racer diameter in px on the delivered 1080x1920 frame; "visible" is racers in
frame and not behind the course; "ahead" is the share of the racing line
downstream of the pack that is in the picture, and how far downstream the
viewer can see in layout units.

| phase | sec | px | visible of 8 | ahead | ahead units |
|---|---|---|---|---|---|
| opening / start | 4.02 → 3.49 | 75 → 75 | 6.21 → 6.30 | 0.00 → 0.45 | 0 → 39.2 |
| first descent | 3.18 → 2.05 | 61 → 48 | 6.37 → 6.76 | 0.01 → 0.38 | 0.7 → 17.2 |
| obstacle | 3.70 → 5.43 | 114 → 69 | 7.15 → 6.40 | 0.06 → 0.46 | 2.8 → 36.4 |
| fork | 2.32 → 1.63 | 36 → 48 | 6.75 → 7.53 | 0.08 → 0.42 | 3.8 → 21.1 |
| branches | 1.40 → 1.68 | 49 → 34 | 2.57 → 7.00 | 0.17 → 0.25 | 9.6 → 34.5 |
| merge | 1.13 → 1.78 | 40 → 28 | 2.75 → 4.94 | 0.33 → 0.21 | 15.3 → 10.5 |
| finish | 3.40 → 4.27 | 60 → 60 | 1.14 → 1.21 | 0.21 → 0.21 | 13.4 → 11.5 |

**The one number that says what V22 is.** Track-ahead across the race goes from
essentially nothing — V21 showed 0 to 4 layout units of the course in front of
the pack over the whole descent, fork and obstacle — to 17 to 39 units. That is
the difference between watching marbles arrive somewhere and watching them
approach something.

**Obstacle.** The restoration works: approach, entry, interaction, struggle,
escape and exit are all on screen, and the leader's escape into leg3 at replay
14.9958 — which V19 through V21 cut to black just before — is in the film. The
price is scale: V21's obstacle shot was 8 units wide and 114 px a racer, the
biggest in any edition. At 69 px it is still well over the 48 px floor, and it
buys `ahead_units` 2.8 → 36.4, which is the whole beat. Occlusion rises 0.037 →
0.124, the chase's worst, because a camera behind the pack has the spinner frame
between it and some marbles.

**Fork.** Better on every axis: 47.8 px against 35.9, 7.53 racers visible
against 6.75, both routes in frame in every sampled frame of both editions, and
21.1 units of track ahead against 3.8.

**Branches.** 2.57 racers visible becomes **7.00** and occlusion falls 0.100 to
0.017. The cost is 49 px to 34 px.

**Merge.** 2.75 visible becomes 4.94 and occlusion halves, 0.421 to 0.191. The
cost is 39.7 px to 28.4 px, which is under the 48 px phone floor and is the
film's weakest framing.

## 9. The merge, and what did not work

Both problems the brief flags at the merge — the 28 px scale and the 0.443 cut
into the finish — were attacked and neither moved.

**Elevation and trail do not buy scale here.** Swept over trail 18/22/26 and
rise 22/26/30/34, the whole reachable range is 28.4 px to 32.8 px, and every px
gained costs visibility: at trail 18 / rise 22 the racers are 32.8 px but only
4.07 of 8 are visible against 5.00, and occlusion rises 0.19 to 0.22. The
`MergeCatch` is a basin whose rim stands above a marble's centre, so a lens that
is not looking down into it is looking at its wall. **The shipped set-points are
already the best point of that trade**, and the 28 px is structural.

**The merge-to-finish cut cannot be eased away.** Across that same sweep the
jump moves only between 0.443 and 0.475, because what sets it is the *finish*
lens — a low, close, almost-directly-behind shot at bearing 170 and 12 degrees —
against a chase 34 units up looking down into the basin. An opt-in blend easing
the chase's tail onto the finish pose was written and measured: it takes the
jump to 0.000 and replaces it with a **whip inside the merge shot**, 2.5 to 6.6
layout units in a single frame against the 1.2 a chase may, which `check_chase`
correctly calls "a cut in the middle of a shot". Getting under the limit would
need a blend longer than the merge phase itself. Trading a clean cut for a whip
is a worse picture, so the mechanism was reverted and the cut stays.

V22 still improves it: 0.605 to 0.443, and it is now the film's only cut.

## 10. Audio

Retimed, not redesigned. Everything is derived from the same replay and the same
clock; the only structural change is one the edit made for it.

    23.0500 s, 48 kHz, synthesised only
    placed: ambience 1, rolling 1, gate 1, tension 1, trapdoor 1,
            whoosh 1, impact 220, split 2, crossing 8, music 1
    integrated -14.15 LUFS, loudness range 4.90 LU, true peak -1.77 dBTP
    compressor 4.72 dB, safety limiter idle

**One whoosh, because there is one omission.** `presentation.omissions` reads
the edit map rather than a list, so removing the spinner omission removed its
whoosh with no edit to the soundtrack. The restored obstacle is now carried by
its own contact cues instead of being masked by an edit sound.

**Eight crossings have sound.** V21 placed six; the two late ones had no output
time to land on. The winner is still the loudest crossing (-1.82 against -4.15
for second) and the loudest moment in the film is 19.53 s against a crossing at
19.42 s.

**One deviation from the brief's figure.** True peak is -1.77 dBTP against the
-1.0 to -1.6 asked for. It is not a tuning: `master(trim=True)` spends leftover
headroom bounded by `MASTER_MAKEUP_MAX_DB = 9.0`, and V22's mix arrives quiet
enough that the cap binds before the -1.3 dBFS ceiling is reached. Lifting the
cap is a change to the soundtrack architecture, which this pass is explicitly
not for; -14.15 LUFS is on target and -1.77 dBTP is under the delivery ceiling
with room to spare, so it was left and recorded.

## 11. Overlays

Three, all derived through the clock rather than typed.

    PICK ONE       2.10 - 2.80     (prefix + 0.10 to prefix + 0.80)
    winner ring   19.617 - 20.317  (crossing + 0.20, 42 frames, on marble 5)
    FROM 6TH -> 1ST  22.40 - 23.05

The hook's numbers are offsets into the **held frame**, not into the file: they
move with the hold so the preview plays clean, and with `prefix = 0` they are
the numbers V20 and V21 have always had. The winner ring comes out of
`clock.at(crossing)` and needed nothing.

The end card overlaps the 7th and 8th crossings at 22.883 and 22.983. That is
intended and not the defect PART 11 names: `overlays.end_fact` is a lower-third
strip — "one fact, low in the frame, under the line the sixth racer is
crossing" — not a card the picture cuts to. The picture itself runs to the last
crossing and past it.

No leaderboard, no HUD, no country labels, no route labels.

## 12. Two bugs fixed

**The frame-indexed cut boundary (`sloped_race_scene.gd`).** Reproducible: a
camera track whose cuts are bounded by frame index duplicates a frame at each
join, because `to` is written to six decimals and the scene's clock is
`frame / fps` at full precision, so the frame falls through to the next cut and
is drawn with that cut's row zero. The course-preview pass worked around it in
the track it writes; the renderer now fixes it. It steps back when the wanted
second is before the chosen cut's first row, with a **half-frame tolerance** —
the other half of the fix, because the row times are rounded too and a
no-tolerance step-back over-corrects in the other direction.

It is a no-op on the production track: over all 1150 frames of V21's, the chosen
cut is identical before and after, so V19, V20 and V21 still render what they
rendered. Both halves are pinned by
`tests/test_sloped_v22_integration.py::test_the_boundary_fix_*`.

**`_dusk_band` (`course_world.gd`).** `look_at` reads a node's *global*
transform and every node in that file is still detached — `build` makes `root`
with `Node3D.new()` and returns it — so Godot printed an error for each of the
nine horizon slabs and left them all at the identity, facing bearing 0. The warm
horizon band has been edge-on over most of its arc since before V21. Moving
`add_child` earlier does not help, because `root` is never in the tree at all;
the fix is a yaw, which is exact rather than an approximation: `_polar` puts the
slab at `(sin b * r, y, cos b * r)` aiming at `(0, y, 0)`, so `look_at` would
point -Z at `(-sin b, 0, -cos b)`, and a yaw of `b` sends +Z to `(sin b, 0,
cos b)` — the same orientation, no tree needed. `_clouds` has posed its slabs
this way all along.

## 13. Visual contrast

Unchanged. V21's grade is the race scene's own default and V22 renders under it
with no flag. QC measures the delivered file at a darkest frame of 62.6 luma
with no black frames. The preview does show parts of the environment no earlier
edition framed — the far hillside above the branch lobes, and the horizon band
the `_dusk_band` fix restored — and nothing in them needed a presentation fix.

## 14. Runtime

    preview   120 frames    2.000 s
    hold       42 frames    0.700 s
    race     1221 frames   20.350 s
    film     1383 frames   23.050 s

Inside the brief's 22.8–23.3 s, and not aimed at: the start stops where churn
stops, the two restorations are the two live stretches the film omitted, the
preview is 120 frames, and 23.050 s is what those add up to.

## 15. Tests

    tests/test_sloped_v22_pacing.py          the pacing prototype's own suite
    tests/test_sloped_course_preview.py      the preview prototype's own suite
    tests/test_sloped_chase.py               the chase prototype's own suite
    tests/test_sloped_v22_integration.py     24 tests, new, the joins between them

The integration suite asks the questions that only exist once the three are
together: that the prefix is frames over fps, that no replay second maps into the
preview, that `replay_at` says nothing there and the master's first frame during
the hold, that the prefix is a pure translation of the race clock, that the film
never repeats or rewinds, that there is exactly one omission, that V21's clock is
untouched, that `EDIT_V22` is the recommended timeline and the seven windows it
does not touch are V21.2's exactly, that every lens is V21.2's but the start's
orbit, that all eight crossings are in the film and that V21 really did cut two
of them, that the preview lands on the race camera's first pose, and that the
renderer's boundary fix repairs a frame-indexed track and cannot disturb a
station-bounded one.

**Full suite on this branch: 2072 passed, 4 skipped, 1 failed in 5:20.** The
failure is `tests/test_neon_proof.py::test_a_missing_godot_is_reported_rather_
than_raised`, which is the same environmental case V21 recorded: in a clean
worktree `output/neon_v11/neon_7.json` does not exist, so the tool reports the
missing replay before it ever reaches the Godot check the test is asserting on.
Nothing in V22 touches `neon_proof`.

## 16. QC

`python tools/sloped_short.py --edition v22 --stage qc` — every check passes.

    [pass] 1080x1920, 60/1 fps, 1383 frames = 23.0500 s
    [pass] runtime 23.050 s inside 22.8-23.3
    [pass] true peak -1.77 dBTP (ceiling -1.0), integrated -14.15 LUFS
    [pass] the winner's crossing is the loudest crossing
    [pass] the safety limiter stayed idle
    [pass] no black frames (darkest 62.6 luma)
    [pass] mpdecimate keeps 1348 of 1383 frames
    [pass] the held opening is one still picture (mean difference 0.0028)
    [pass] the winner's mark ends at 20.32 s, before the 21.20 s dead heat
    [pass] the hook is gone by 2.80 s; the gates first move at 2.817 s

Two QC checks had to learn about the prefix, and both were reporting correctly
about the wrong frames until they did: the held-opening stillness test was
comparing frames 2 and 40, which in V22 are *preview* frames, and reported a
mean difference of 66.3 with 99.9% of pixels moved — a correct reading of two
frames of a moving shot. It now takes an offset. The hook's deadline was a bare
0.80 s, which is a moment inside the preview; it is now `prefix + 0.80`.

## 17. Phone-size review

Rendered at 1080x1920 and reviewed at 270x480
(`docs/validation/sloped_race_v1/v22_final/phone.jpg`).

| question | verdict |
|---|---|
| Does the preview communicate the challenge? | **Yes.** Finish, the long descent, the branch pair and the machine all read, and it ends on a line of eight marbles. |
| Can I pick a marble? | **Yes**, and better than any edition. The preview delivers you to the lineup and the hold freezes on it. |
| Is the shuffle satisfying? | **Yes.** 1.583 s of visible mixing with the marbles clearly separate in the drum. |
| Is the release exciting? | **Adequate.** The trapdoor frame is scenery-heavy and the drum sits in the upper third. |
| Can I see where they are going? | **Yes** — this is the biggest change. 17 to 39 units of track ahead where V21 had 0 to 4. |
| Obstacle: coming, interaction, escape? | **Yes, all three.** The approach frame — the whole spinner bank in shot with the track leading into it — is the best in the film. |
| Do I understand the fork? | **Yes**, though the divider reads later than the phase name suggests; the separation is clearest at 15.4–16.1 s. |
| Can I follow the branches? | **Partly.** Both routes and all eight racers are in frame, but at 34 px (about 8 px at 270 wide) identity is hard. |
| Do I understand the merge? | **Yes** at full size — two tracks visibly converge at 17.1–17.7 s. **Weak at phone size**, 28 px. |
| Can I identify the winner? | **Yes.** The FINISH sign, the ring, and the winner's own hue on the end card. |
| Do I have time to process? | **Yes.** Eight shots over 23 s, longest 5.4 s. |

## 18. Known weaknesses

1. **Merge scale, 28.4 px.** Under the 48 px phone floor. Measured as structural
   (section 9); a fix needs geometry or a different shot, not a set-point.
2. **Branch scale, 34 px.** The price of showing 7.00 racers instead of 2.57.
   Zooming in loses a route, which the brief rules out.
3. **Headroom in the fork phase.** Roughly the top third of those frames is
   unlit mountain. A larger `look` on that phase would push the pack down the
   frame; not attempted here because each trial costs a full re-render to judge
   and the measured numbers are already good.
4. **Obstacle occlusion up**, 0.037 → 0.124, and scale 114 px → 69 px. The
   deliberate price of seeing it coming.
5. **True peak -1.77 dBTP**, 0.17 dB outside the asked range, bound by the
   master makeup cap (section 10).
6. **The merge → finish cut, 0.443.** Improved from 0.605 but not removable
   (section 9).

## 19. Should V22 replace V21?

**Yes, on the measurements — but watch it first, which is why this branch is not
merged.** V22 is better than V21 on every question the brief asks except racer
scale in two phases: it shows the course ahead where V21 showed none, it has one
cut where V21 had three hard ones, it puts back 0.9 s of the highest-churn
footage in the race and lets all eight marbles finish, and it opens with two
seconds that tell the viewer what they are about to watch. The two regressions
are both "the racers are smaller in a wide shot", both were bought deliberately,
and one of them replaced 2.57 visible racers with 7.00.

The thing numbers cannot settle is whether 23.0 s of one continuous camera reads
as an experience or as a long take. That is what the review is for.

## 20. Reproducing it

    python tools/sloped_v22.py --stage all --godot PATH     # solve, freeze, render
    python tools/sloped_short.py --edition v22 --stage all  # audio, overlays, mux, qc
    python tools/sloped_v22_metrics.py                      # the numbers in section 8
    python tools/sloped_v22_sheet.py --stage all            # the comparison material

`output/sloped_race_v1/race_5432.json` is generated output and is not in the
branch; copy it from a tree that has it. The render is 1221 + 120 frames at
about 400 ms a frame — roughly nine minutes on an RTX 3050.

The committed validation stills are JPEG at quality 88 with no chroma
subsampling, which is 3.0 MB against 20.1 MB of PNG. The lossless originals are
in `exports/v22_integration/validation/`. They were briefly written as 256-colour
PNGs instead, which is a quarter of the size again and posterises exactly the
smooth gradients a contrast review is looking at; that was reverted.

Validation material is in `docs/validation/sloped_race_v1/v22_final/`:
`metrics.json`, `sheet.jpg`, `phone.jpg`, `timeline.jpg` and seventeen
`pair_*.jpg` — V21 beside V22 at the same *replay* instant, since the two films
do not share a clock. Three of the pairs show V21 as "not in this film": the
restored mixing at replay 1.60, the restored spinner escape at 15.00, and the
last crossing at 24.42.
