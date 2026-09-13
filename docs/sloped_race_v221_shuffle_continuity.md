# V22.1 — shuffle continuity: why the start reads as a jump, and what actually fixes it

**Branch** `v221-shuffle-continuity`, cut from `origin/v22-integration` at
`57d50da`. Nothing here re-simulates, retimes, interpolates or re-seeds. Seed
5432, digest `aafb0d3d…`, finish order 5, 2, 7, 4, 1, 6, 3, 0 — all unchanged and
all asserted in `tests/test_sloped_v221_shuffle.py`. `ShuffleFloor` is not
touched. Every window edge in every plan is a real replay frame.

---

## The short version

The brief asked for a balance between showing more real shuffle and hiding the
remaining omission. Measured, the balance is not where it was thought to be,
because **the omission was never the biggest thing that changes at the join.**

At V22's cut — replay 1.900 to 5.833333 — three things change at once:

| what changes | by how much |
| --- | --- |
| the camera | jumps **5.374 layout units** in one frame and pulls back **3.663**, against **0.851** for the largest step anywhere inside either shot |
| the rotor | **stops dead** (it was turning at 13 rad/s, 2.07 rev/s) and **rises 1.193 sim units** out of the drum |
| the marbles | move up to 2.322 sim units — **1.91 marble diameters** on screen |

The marbles are the smallest of the three. A viewer reporting "the video jumped"
is reporting the camera and the rotor.

Measured on the rendered frames, V22's join is the **single largest picture
change in the whole start** — 57.90 mean absolute luma against a median of 3.54
between neighbouring frames, a ratio of **16.4×**, rank 1 of 209.

> **A note on "3.933" against "3.917".** The gap between the two window edges is
> 5.833333 − 1.900 = 3.933 s, which is what `cameras`' own `omitted` field
> carries and what the brief quotes. One frame of that gap is the step playback
> would have taken anyway, so the replay **nobody ever sees** is 235 frames =
> 3.917 s. Both readings appear below; the tables use the strict one and label it
> `omitted`, and `StartPlan` exposes both.

Three changes therefore need three answers, and none of them is a wipe:

1. **Make the camera continuous.** One constant-rate move across the whole
   start, split between the windows so the second opens on the value the first
   closed at *and* carries on at the same speed. Join step: **0.000 units.**
2. **Phase-lock the rotor.** Move the omission inside the constant-rate spin and
   make it a whole number of revolutions — 29 frames each at 60 fps. The blades
   are then within **0.034°** of where a normal frame would have put them, and
   the paddle assembly is at exactly the same height. The rotor keeps turning
   through the cut.
3. **Stop the shot climbing a staircase.** A defect this pass found on the way
   past and did not go looking for — see below.

With all three, the omission stops being the biggest event in the shot and
becomes an ordinary frame.

---

## The machine's own timeline, which is what the edit should have been cut against

`ShuffleFloor` is a five-beat device and every beat is a pure function of
`release_time`. Read off the module rather than typed:

```
0.300          the start gate opens; the field pours down the apron
0.300 - 1.600  the pour. 14 marble-on-marble collisions, the loudest at 9.08
1.600          rotor_start — held until the whole field is in, so every racer
               gets the same number of degrees of rotor
1.600 - 4.600  the mix: 13.0 rad/s, 6.21 revolutions, CONSTANT RATE
4.600 - 4.900  spin_down — the blades visibly decelerate to a stop
5.200 - 5.900  rotor_lift_time — the paddle assembly rises out of the drum,
               1.193 sim units, on a smoothstep
5.900 - 6.100  nothing moves at all
6.100          gate_time — the trapdoor opens
6.213          the first collision since 2.013
```

Beats four, five and six **are** the anticipation the brief asked for, and they
were already in the physics: the mixer winds down, the machine withdraws its own
blades, everything goes still, and then the floor goes.

**V22 omits all three of them.** Its second window opens at 5.833333, which is
0.267 s before the trapdoor with the blades already up and still. Of the 1.500 s
between the rotor stopping and the floor opening, V22 plays 0.267.

That is the real cost of the current cut, and it is larger than the runtime it
saves.

### And the marbles were never mixing anyway

Between replay **2.013 and 6.213 there is not one marble-on-marble collision** —
a 4.2-second gap in an events list that has 112 of them. Mean marble speed over
that stretch runs 0.6 sim units/s falling to a flat 0.43, which is 0.7 % of a
marble diameter per frame. The field is carried slowly round the drum by the
blades; it does not tumble.

So "showing more mixing" cannot mean showing more marble motion, because after
2.0 s there is none to show. What the stretch actually contains is a spinning
rotor over a nearly-static field — which is why the *rotor* is the thing the
edit has to be continuous in.

---

## The phase lock

Between `rotor_start` and `rotor_stop` the rotor turns at exactly 13.0 rad/s, so
a blade's screen position is periodic:

```
one revolution = 2π / 13.0 = 0.483322 s = 28.9993 frames at 60 fps
```

29 frames is 0.483333 s — **0.0085° of blade**. The four blades are identical
and 90° apart, so a quarter turn would do in principle, but at 60 fps a quarter
turn is 7.2498 frames and only whole revolutions land near an integer:

| revolutions | frames | seconds | blade error |
| --- | --- | --- | --- |
| 1 | 29 | 0.4833 | +0.0085° |
| 2 | 58 | 0.9667 | +0.0170° |
| 3 | 87 | 1.4500 | +0.0254° |
| 4 | 116 | 1.9333 | +0.0339° |
| 5 | 145 | 2.4167 | +0.0424° |

Two conditions make the lock work, and the second is easy to forget: the
omission must be a whole number of revolutions **and** lie entirely between
1.600 and 4.600, because outside that span the rate is not constant and a
revolution is not a revolution.

Verified against the replay's own recorded actuator poses, not against
`shuffle.Rotor`'s law: every B plan's join advances `start.rotor0` by one frame's
worth of rotation to within 0.05°, and changes its height by exactly 0.0000.

**The trade curve is shallow and that is the finding that decides the pass.**
Each revolution omitted buys 0.483 s of runtime and costs about a quarter of a
marble diameter of arrangement change:

| plan | omitted | start runtime | worst marble jump | live mixing |
| --- | --- | --- | --- | --- |
| `c` (none) | 0.000 s | 7.420 s | 0.00 d | 3.000 s |
| `b58` | 0.967 s | 6.437 s | 0.64 d | 2.017 s |
| `b87` | 1.450 s | 5.953 s | 0.87 d | 1.533 s |
| `b116` | 1.933 s | 5.470 s | 1.12 d | 1.050 s |
| `b145` | 2.417 s | 4.987 s | 1.32 d | 0.567 s |
| `v22` | 3.933 s | 3.487 s | 1.91 d | 0.300 s |

---

## Strategy A — more live replay — is falsified

Keeping more replay before the omission and leaving the far side at 5.833333
cannot work, and the reason is structural rather than a matter of degree: **the
far side is after the rotor has stopped and lifted**, so the join is across a
change in the machine's state that no amount of near-side time reconciles.

`a25` — 2.300 s of live replay, 0.767 s more than V22 — measured on its own
rendered frames:

```
join picture change   57.79   median neighbour 3.07   ratio 18.83x   RANK 1 of 245
```

The ratio is *worse* than V22's, because the extra live time lowers the median.
The join is still the single largest change in the clip. `a22` and `a28` are in
`PLANS` and behave the same way; `a28`'s omission happens to be a whole number of
revolutions by luck, and it makes no difference at all, because after 4.900 the
rotor has no phase to match — it has a *stop angle*.

**This is the general result: churn on the near side of a cut does not predict
whether the cut is visible.** V22's pacing pass chose 1.900 because churn fell
through the floor there, and chose the far side because "the field has already
settled". Both ends are settled by that measure, and the join is still the worst
frame in the film — because churn measures the marbles, and the marbles were the
smallest of the three things that move.

---

## Strategy B — the occlusion wipe is not available, and does not need to be

The brief's Strategy B asked whether the camera could slide behind a paddle or
the housing rim, cut while the frame is obscured, and emerge on the settled
field. Measured at the shipped start framing — extent 14, fov 34, a 21.5-unit
reach, 1080 × 1920 — it cannot:

* **The blades are too small.** Each projects as roughly 200 × 150 px, which is
  two marbles' worth on a frame 1920 px tall. Swept over every phase of the
  rotor, the best single frame covers **27.9 %** of the field's projected area,
  and that figure is measured with each blade's *bounding rectangle*, which
  over-states a thin blade seen at an angle. At the chosen joins, blade coverage
  of the field runs 7.6 % to 13.9 %.
* **The rim is too low.** The chamber wall stands 0.62 layout units above a floor
  the lens is 10.8 units above. To put that rim between the lens and the field
  the elevation has to come down to a couple of degrees, at which point the shot
  is looking through the machine at the mountain — and `cameras.build_track`'s
  own clearance loop raises it straight back, because it only ever lifts.

There is no other element in the start module big enough. A foreground object
that fills a 34° frame at 21.5 units has to be about 13 units across; the biggest
thing in the module is the 5.8-unit drum the shot is *of*.

**So the wipe was dropped, and the goal it was for was met another way.** What
Strategy B was really asking for is that the frame should not change at the
instant the replay clock jumps. Hiding the subject is one way to get that. Making
the subject continuous is a better one, and the phase lock makes the largest and
fastest-moving object in the frame continuous for free.

### The camera, which turned out to be the dominant cause

V22's two start windows do not share a camera. The first orbits from −36° to +4°
of bearing offset and dollies from +0.10 to −0.06 of reach; the second **starts
over** at the start lens's own −6° and +0.10. So at the join the lens swings back
10° and pulls out 17 %, all in one frame: 5.374 units of position and 3.663 of
reach.

`constant_rate_legs` fixes it by treating the whole start as one move and
dividing it between the windows in proportion to their lengths. Both ends are
unchanged — it still opens at `cameras.V22_START_ORBIT`'s −36° for the preview
handoff and still closes on the +4° and −0.06 that `cameras.SECTIONS`' start cut
was proved at, so the launch is framed on the pose V21.2 measured. All that
changes is that the 40° is spent at one rate instead of two.

The result is continuity in **position and velocity**: the join step is 0.0000
units, the reach change 0.0000, and the lens arrives at the boundary moving and
leaves it moving the same way.

**The ablation says the camera was the dominant cause.** `b116_jumpcam` is the
phase-locked join — same frames, same rotor, same marbles — with V22's
discontinuous legs put back:

| | join change | median | ratio | rank in clip |
| --- | --- | --- | --- | --- |
| `b116` (continuous lens) | 3.58 | 2.29 | 1.56× | 10 of 328 |
| `b116_jumpcam` (V22's lens) | **50.71** | 2.01 | **25.2×** | **1 of 328** |

Identical frames, identical rotor, identical marbles. Put V22's legs back and the
join goes from an ordinary frame to the single largest change in the clip.
**The camera accounts for 93 % of the residual jump.**

---

## The defect this pass found on the way past: the clearance staircase

`cameras.build_track` raises a cut's elevation, frame by frame, until the sight
line clears the ground by `SIGHT_MARGIN`. It does it in whole `LIFT_STEP` of 2°,
and nothing smooths the result. On the start lens's own 16° that loop engages
part-way through the shot and then keeps engaging, and **each engagement moves
the lens 0.79 to 0.87 layout units in a single frame.**

The delivered V22 start has nine of them:

```
cameras_v22_5432.json, start cut 0:  steps of 0.851 0.842 0.834 0.826 0.814 0.792 0.771
cameras_v22_5432.json, start cut 1:  steps of 0.870 0.787
```

On the rendered frames each one changes the picture about ten times as much as an
ordinary frame does — 34.5 and 40.2 against a median of 3.5, the second and third
largest changes in the V22 start after the join itself.

They are not the omission, `cameras.check_track` does not report them, and they
are why the start reads as unsteady quite apart from the join.

The prototype avoids them without touching `cameras.py`: it sets the start
windows' `elevation` to 30°, which is where the loop was taking the shot anyway,
so the loop never runs. **The largest lens step anywhere in the start falls from
0.837 units to 0.044** — a factor of 19 — and the framing is the same shot: 8
racers of 8 at 77 and 82 px against 78 and 83.

**Production recommendation, out of scope for this branch:** either smooth
`lifts` the way `aims` and `headings` are smoothed in `build_track`, or make
`LIFT_STEP` continuous. Nine 0.85-unit lens jumps are in the delivered film.

---

## What the numbers say about the join

Measured on the rendered frames of each proof clip: the mean absolute luma
difference between the two frames either side of the join, against the median
difference between every neighbouring pair in the same clip, and the join's rank
among all of them.

| plan | screen | live mixing | omitted | join change | median | ratio | **rank in clip** | biggest change anywhere |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `v22` control | 3.487 s | 0.300 s | 3.917 s | 57.90 | 3.54 | 16.35× | **1 of 209** | 57.90 |
| `a25` strategy A | 4.087 s | 0.900 s | 3.317 s | 57.79 | 3.07 | 18.83× | **1 of 245** | 57.79 |
| `b116_jumpcam` | 5.470 s | 1.050 s | 1.933 s | 50.71 | 2.01 | 25.21× | **1 of 328** | 50.71 |
| `b145` strategy B | 4.987 s | 0.567 s | 2.417 s | 3.96 | 2.43 | 1.63× | 9 of 299 | 5.08 |
| `b116` strategy B | 5.470 s | 1.050 s | 1.933 s | 3.58 | 2.29 | 1.56× | 10 of 328 | 4.98 |
| `b87` strategy B | 5.953 s | 1.533 s | 1.450 s | 3.69 | 2.18 | 1.69× | 9 of 357 | 4.83 |
| `c` no omission | 7.420 s | 3.000 s | 0.000 s | — | 2.12 | — | — | 4.69 |

Read the last two columns together. In `v22` and `a25` the join is the **largest
single picture change in the whole start**, 16 to 19 times an ordinary frame. In
every B plan the join is a few places down a list whose top entries are the
trapdoor opening — and the biggest change anywhere in a B clip (4.8 to 5.1) is
within 8 % of the biggest change in the clip that omits **nothing at all** (4.69).

**The B start is as steady, frame to frame, as a start with no edit in it.**

Two things fall out of this that were not expected:

* **Perceptibility is flat across the B family.** 2, 3, 4 and 5 revolutions all
  land between 1.56× and 1.69×, even though the worst marble jump goes from 0.64
  to 1.33 diameters over that range. The arrangement change is simply not what a
  viewer's eye is catching. So the choice between them is **purely a runtime
  decision**, not a quality one.
* **The whole clip got steadier, not just the join.** The B clips have no
  neighbour change above 5.08 anywhere; the V22 start has the join at 57.90 and
  then two clearance-staircase steps at 40.2 and 34.5.

---

## Settling is not dead, but four seconds of it is a lull

Strategy C was run as a control and watched. The honest reading:

* Between replay 2.013 and 6.213 there is **no event**: no collision, no module
  change, mean marble speed flat at 0.43 sim units/s. The only things moving are
  the rotor and the camera.
* It is not *dead* — the camera's own orbit keeps the composition changing, the
  drum opens up as the terrain wedge slides out of frame, and the blades turn.
* But 4.2 s of it is a long hold in a film whose race body is about 15 s, and
  nothing in it builds. The build is in the last 1.5 s — wind-down, blade lift,
  stillness — and those are worth every frame.

So the brief's instinct is right and its arithmetic is the other way round: the
quiet has narrative value, and the quiet that has it is **the 1.5 s before the
drop**, not the 2.5 s of idling in the middle. The B plans keep all of the first
and spend the second.

---

## Recommendation

**Ship `b116`.** Replay 0.200–2.050 live, 116 frames omitted, 4.000–7.620 live.

| | V22 | V22.1 `b116` |
| --- | --- | --- |
| start on screen | 3.487 s | **5.470 s** |
| live mixing (rotor turning) | 0.300 s | **1.050 s** |
| wind-down, blade lift and stillness before the drop | 0.267 s | **1.500 s** |
| replay omitted | 3.917 s | **1.933 s** |
| omissions | 1 | 1 |
| join, against an ordinary frame | 16.35× | **1.56×** |
| join's rank among picture changes in the clip | 1 of 209 | **10 of 328** |
| largest lens step anywhere in the start | 0.870 units | **0.044 units** |

It shows 3.5× the live mixing, 5.6× the anticipation, halves the omission, and
the cut stops being visible. It costs **1.983 s** of runtime.

**The dial, if that runtime is not available.** Because perceptibility is flat,
the reviewer can move along the B family freely and lose only shuffle, never
continuity:

* `b145` — 4.987 s, 0.567 s of live mixing. Only 1.500 s longer than V22, and
  the join still measures 1.63×. This is the setting to take if the film's total
  runtime is the binding constraint.
* `b87` — 5.953 s, 1.533 s of live mixing. Half a second more than `b116` for
  50 % more mixing on screen. Take this if the reviewer wants the drum to read
  as a drum.
* `c` — 7.420 s, no omission at all. **Not recommended**, and the control is what
  says so rather than an opinion: it holds 4.2 s in which the events list is
  empty and the mean marble speed is flat at 0.43 sim units/s. It is not dead —
  the camera's orbit keeps the composition moving — but 2 s of the middle of it
  build nothing, and `b116` buys those 2 s back for a join nobody can see.

Every one of them keeps the two boundaries the film needs: in at replay 0.200 on
the preview's handoff pose, out at 7.620 where `chase_camera` takes over.

---

## Audio

**At the join: no transition sound.** This is a change of advice from V22 and it
follows from the measurement rather than from taste. `audio/marble.py` derives a
whoosh from `presentation.omissions(clock)` automatically, and its comment is
explicit about why it exists — "without a cue it reads as a glitch". That
premise no longer holds: the join is an ordinary frame, so a whoosh would not
excuse a discontinuity, it would *announce* one the picture does not have. The
strongest argument against it is `v22_timeline.cut_on_motion`'s own: a cue that
contradicts the picture is worse than no cue.

Integration note: suppress it by giving the whoosh a minimum omission — below
about 2.5 s of omitted replay, place nothing — rather than by hand-muting one
cue, so the rule travels with the edit.

**The mixer's own sound should be a drone, not contacts.** There are no
marble-on-marble collisions at all between 2.013 and 6.213, so a contact-led
mixing texture has nothing to fire on. What the drum is actually doing is turning
at a constant 13 rad/s with four blades — 8.28 blade passes a second. A steady
rotor drone from 1.600 does two jobs at once:

* it covers the join for free, because a steady drone has no phase to break —
  the same argument as the phase lock, one layer up;
* it makes the **wind-down audible**. Pitching it down through 4.600–4.900 and
  out is the single strongest anticipation cue available, and it is derivable
  rather than placed: `rotor_stop` and `SPIN_DOWN` are on the module.

**Two placed cues, both real machine events:**

* **5.200–5.900, the blade lift.** A servo or rising cue under the paddle
  assembly withdrawing. This is a beat V22 never showed, let alone scored.
* **6.100, the trapdoor.** Already derived — `pres.actuator_move(replay, clock,
  "start.panel")` — and it lands 0.200 s after the machine has gone completely
  silent, which is what makes it land.

The pour keeps its contact cues: 14 collisions between 0.621 and 2.013, the
loudest at 9.08 relative speed.

---

## Integrating this into the film

Five changes, all inside `sloped/cameras.py`'s V22 edit plan and
`chase_camera`'s bookend. Nothing outside the start moves, and the chase, the
merge, the finish and the whole soundtrack keep their output times **relative to
the start's new length** — which is the one thing to be careful about, because
the start gets 1.983 s longer and everything after it shifts by that amount.

**1. The windows.** In `cameras._V22_WINDOWS`, replace the two start entries:

```python
("start", 0.20): 1.900,                    -->  ("start", 0.20): 2.050,
("start", 5.70): (5.833333, 7.620),        -->  ("start", 5.70): (4.000, 7.620),
```

Both new edges are real replay frames — 2.050 is frame 123, 4.000 is frame 240 —
and the gap between them is 116 frames, four whole rotor revolutions.

**2. The camera legs.** `_v22_edit` currently puts `V22_START_ORBIT` on the
first start window only and leaves the second on the lens's own `orbit=(-6, 4)`
and `dolly=(0.10, -0.06)`. Replace that with the two legs
`v221_shuffle.constant_rate_legs` computes for the window lengths 1.850 s and
3.620 s:

```python
window 1   orbit (-36.0, -22.471664)   dolly (0.10, 0.045923)
window 2   orbit (-22.471664, 4.0)     dolly (0.045923, -0.06)
```

Do not hard-code those if the window edges may move again — call
`constant_rate_legs(window_spans(plan), ORBIT_TRAVEL)` and the same for
`DOLLY_TRAVEL`, which is what keeps the two properties true by construction.

**3. The elevation.** Add `"elevation": 30.0` to both start windows' overrides.
This is the clearance-staircase fix and it is worth taking on its own merits even
if none of the rest is adopted.

**4. The preview.** `v22.build_preview_track` already re-solves the preview onto
`handoff_pose(race_track)`, so the preview follows the new first pose with no
edit. Re-run `tools/sloped_v22.py --stage solve` and check `report["problems"]`
is empty — the first pose moves by about 1.6 layout units, well inside what the
end blend absorbs, but it is the one thing here that is not proved in this
branch because the brief put the preview out of scope.

**5. The soundtrack.** See below. The one code change is a floor on the whoosh.

**What to re-render:** the race master only. The preview master is 120 frames of
its own footage and is unaffected except for its last pose.

**What must not change:** replay 0.200 in, 7.620 out, seed 5432, and the
`descent` window opening at 7.620. `tests/test_sloped_v221_shuffle.py` asserts
the first two directly.

**One observation for whoever does the integration**, found while watching and
not introduced by this pass: the start shot's last second holds an **empty
chamber** — the field is through the chute by about replay 6.6 and the window
runs to 7.620. V22 has exactly the same tail. It is a separate pacing question
and this branch did not touch it.

## Files

| file | what it is |
| --- | --- |
| `sloped/v221_shuffle.py` | the plans, the phase-lock solver, `constant_rate_legs`, and the join measurements |
| `tools/sloped_v221_shuffle.py` | solve / render / contact sheet / table |
| `tests/test_sloped_v221_shuffle.py` | the time claims, the phase lock against the recorded poses, and the race identity |
| `docs/validation/sloped_race_v1/v221_shuffle/` | the measurements and the transition contact sheets |

`tests/test_sloped_v221_shuffle.py` is 18 tests and they all pass. Run against
the whole `tests/test_sloped*.py` set with the replay and both camera tracks in
`output/`, this branch is **716 passed, 20 failed, 39 errors** — and the failing
set is byte-identical to a pristine checkout of `origin/v22-integration` run the
same way. Every one of them is `ModuleNotFoundError: No module named 'pybullet'`
or `'pymunk'`: this interpreter has neither, and none of the physics packages is
needed by anything in this pass.

Production files named in the brief as off-limits — `sloped/cameras.py`,
`sloped/presentation.py`, `sloped/v22.py`, `sloped/v22_timeline.py`,
`tools/sloped_short.py`, `tools/sloped_short_qc.py` — are untouched. `git diff
--stat` against `origin/v22-integration` shows only additions.
