# The sloped race, corrected

V1 shipped a beautiful course that did not race. This is what was measured,
what was wrong, what was changed, and — for the one target that was not met —
what the measurement says instead.

`docs/sloped_race_v1.md` is the baseline and every number quoted from it is
labelled, because section 18 is explicit that it was taken on a physically
defective course and must not be read as a like-for-like comparison.

---

## 1. What was actually wrong

Three defects, and **two of them were in the instruments** rather than in the
geometry. That is the finding of the session, because it is the reason V1's
report drew a confident conclusion — "the orange route is unreachable, six
divider configurations prove it" — from a measurement that could not have
reported anything else.

### The route attribution could not attribute a route

`sloped.race._locate` chose which runs to search for a marble's position by
filtering on the marble's own route, and fell back to blue while the route was
still open. `_route_from_place` only ever returns `"orange"` for a marble
located on `orange_lead` or `orange` — the two runs the filter excluded. So no
marble could ever be assigned the orange route, and a marble that did cross
east was located on leg3, two channel widths outside it, and booked as having
left the course.

V1's "no configuration ever put a marble on the orange lobe and got it to the
finish" is a statement about this function.

### The split lab retired a marble for going the right way

Written this session and wrong in the same shape: containment was measured
against the run a marble was *located on*, and orange's mouth is a channel
half-width east of leg3's centreline, so a marble crossing correctly onto
orange read as two half-widths outside leg3 and was retired before it could
land. All seven controlled entries reported `leg3[90..95]` for that reason and
not because anything fell off the course. A marble is lost when it is outside
**every** channel.

### The start lab could not see a jam

Also written this session. It counted marbles that left the channel and
marbles that stopped dead, and a paddle wheel at the launch entry produces
neither — it produces marbles grinding along at 4 wu/s with the leader long
gone. The lab scored that wheel 0.55% lost and recommended it; on the real
course it put **18.8% of the field in the stuck column**. `startlab` now
measures whether each marble got *through*, and runs each trial until the field
settles rather than until the leader finishes.

---

## 2. The start: diagnosed exactly, corrected only a little

### Where the bias is made

`sloped.startlab` builds the start, the launch and leg1 alone — 95.7 of the
route's 345.8 simulation units, at a fifth of a full race. Over 400 seeds it
reproduces the full course's 9% checkpoint slot for slot:

| bay | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | span |
|---|---|---|---|---|---|---|---|---|---|
| full course, 600 races | 6.35 | 5.12 | 2.74 | 4.51 | 3.76 | 5.04 | 3.62 | 4.87 | 3.61 |
| the lab, 400 trials | 6.355 | 5.202 | 2.740 | 4.490 | 3.768 | 4.960 | 3.595 | 4.890 | 3.615 |

So the lab is the start, and it costs 1.25 seconds a trial instead of 28.

What it says, measured at four points along the start fan:

| fan position | tick, best bay | tick, worst bay | span |
|---|---|---|---|
| t = 0.25 | 221.0 | 223.8 | **3 ticks** |
| t = 0.50 (the fins end) | 317.6 | 329.0 | 11 ticks |
| t = 0.75 | 398.7 | 434.5 | 36 ticks |
| t = 1.00 (the launch seam) | 476.1 | 551.8 | **76 ticks** |

A quarter of the way down the fan the eight bays are within three ticks of each
other. The entire bias is made in the fan's second half, and the mechanism is
not subtle: the bare converging trough funnels all eight marbles onto one line,
and the queue that forms there is ordered by how far each bay had to travel
sideways to reach it. The outer bays are deflected 46 degrees and arrive at the
seam at 8.2 wu/s against the inner bays' 11.2.

The rest of the course then preserves that order, because it is a 3.3-diameter
channel in which everyone runs at the same terminal speed. By the launch exit
the field is strung out over eighteen simulation units at 51 wu/s — the 0.32
second gap made in the fan, frozen.

**V1's stud row sat downstream of all of this**, on leg1, 1.2 units past the
launch seam. It can deflect a marble. It cannot reorder a field that is no
longer a field.

### Eleven geometries, and the rule they all obey

| candidate | rank span | vs V1 |
|---|---|---|
| V1 | 3.705 | — |
| stud row moved to launch sample 5 | 3.685 | −0.5% |
| bay stagger, gain 0.15 | 5.193 | **+40%** |
| bay stagger, gain 0.30 | 5.947 | +61% |
| bay stagger, gain 0.45 | 6.547 | +77% |
| merge tree in the lane dividers | 3.787 | +2% |
| dividers to 0.65 of the fan | 3.807 | +3% |
| dividers to 0.30 of the fan | 5.453 | +47% |
| three deflector rows, 0.10 tall | 5.235 | +41% |
| three deflector rows, 0.16 tall | **7.000** | the maximum possible |
| three deflector rows, 0.22 tall | jammed the fan | — |

Every static addition made the ordering **stronger**, and they fail for one
reason worth more than the table: *every restriction added to a converging
funnel is another queue, and a queue leaves in arrival order.* A longitudinal
stagger is the standard answer to unequal lane length and it is the worst of
them, because the bias is not a smooth function of bay position — bay 2 is the
best bay in V1 and bay 3 is mid-table — so no smooth handicap cancels it, and
one tuned to cancel it would be an engineered result rather than a physical
one.

### The one mechanism that works, and what it costs

A turning wheel is the only thing scanned whose *output* order is not monotone
in its input order: a marble's wait is its arrival time modulo the blade
period. Four blades at 6.0 rad/s pass every 0.26 s against the 0.32 s spread to
be undone.

At the launch entry, where the field is still one channel-width long, it does
exactly that — rank span 3.71 → **2.33**. It also holds 13% of the field up
doing it, and on the real course that is 18.8% stuck, all at `launch[0]`. A
span bought by jamming a fifth of the field is not fairness.

Faster is worse, not better. On the real course, 16 seeds of eight:

| wheel | finish | escape | stuck |
|---|---|---|---|
| none | 0.906 | 0.031 | 0.062 |
| sample 7, 6.0 rad/s | 0.802 | 0.010 | 0.188 |
| sample 7, 12.0 rad/s | 0.177 | 0.021 | **0.802** |
| sample 24, 9.0 rad/s | 0.922 | 0.016 | 0.062 |
| **sample 32, 9.0 rad/s** | **0.969** | 0.016 | **0.016** |
| sample 40, 9.0 rad/s | 0.930 | 0.016 | 0.055 |

A blade at 12 rad/s bats a 13 wu/s marble back up the channel. A wheel belongs
where the field is faster than its blade tip, and at launch sample 32 it beats
having no wheel at all on every count while still taking the span from 3.705 to
**3.345**.

**That 10% is the honest size of the fairness win.** The start bias is
diagnosed exactly and is not fixed. Section 32's "start bias is substantially
reduced" is **not met**, and §7 says what the residual costs in win rates.

---

## 3. The split: both routes now carry marbles to the finish

Beyond the attribution bug, three pieces of geometry.

### The fork was a roll discontinuity, not a gap

It sits 82 samples along leg3, in the middle of a hairpin banked **26 degrees**
— and `min_radius_layout` says a marble at 43 wu/s needs 24.3 of it to hold the
3.5-unit radius there, so the bank is a requirement and cannot be levelled.
Orange's lead eased up from level like every other run, and two cradles rolled
26 degrees apart have their edges 0.7 to 1.5 simulation units apart in world
height while their centrelines coincide.

That is the trench an orange-bound marble fell into, and it is why six divider
configurations could not fix the fork: **nothing put between two channels helps
when the two are not the same surface.** The lead now starts at leg3's own roll
and decays monotonically to level, carrying no bank of its own — which it can
afford, because its worst radius is 10.5 layout units against the 8.6 that
friction alone holds at 43 wu/s.

### The mouth was under the floor rather than beside it

Orange is to the east and the bank raises the east side, so a mouth on leg3's
centreline is a channel *underneath* leg3's. It is now at the top of leg3's
east bank, where the hook's outward throw actually delivers a marble — and the
fork sorts by momentum: enough speed to ride up the bank takes orange, not
enough stays low and follows leg3 round to blue. Nothing chooses for it, which
is section 8's requirement exactly.

The 1.28 mouth flare goes with it. On the moved mouth it put orange's west lip
a marble diameter above the middle of leg3's channel — a roof over leg3's east
half at 43 wu/s, and 53 of 158 losses over 28 seeds.

### Orange ran uphill

Orange was the only run of the nine that climbed: ten consecutive uphill
samples, 86 to 95, 0.017 layout units of rise, from a Catmull-Rom overshooting
through four control heights inside half a unit of each other. Every other run
is strictly monotone.

The cost is not the 0.017. It is that the grade either side of the bump sits
between −0.06 and +0.01, so a marble arriving at `orange[102]` with 10 wu/s
crawled the flat at 2 to 5 and stopped at `orange[114]`. The fall from control
5 to control 9 is redistributed linearly in horizontal arc length: monotone at
−0.049, which is blue's own tail grade and demonstrably enough, because blue's
marbles finish.

Three heights move by at most 0.145 layout units — a quarter of a marble
diameter — and every x and z is untouched, so the plan curve and the silhouette
are as photographed. `sloped.contract` carries it as a **named deviation with
its own budget** rather than a widened tolerance, and `course_layout.gd` is
kept in step.

### The merge trapped marbles on the sprint's own guard rails

The sprint's two guard rails stood up *inside* the merge apron, leaving a ledge
along the top of each with the apron's roof over it. A marble that strayed
outside the channel while crossing came to rest on it: measured at apron-frame
across +2.337, its centre 0.43 simulation units above the apron floor beneath
it, at 0.52 wu/s. Held there by geometry.

This is also where **V1 lost 319 of its 747 marbles**, every one booked to
`blue[100]`. Both rails are opened over the nine samples the apron covers;
containment there is the apron's own outer walls and roof, which span all of it.

### The controlled entry test

`tools/sloped_split_test.py` is section 10: marbles launched into the fork at
chosen speeds, lateral positions and approach angles, scoring the three
failures separately — the fork not sorting, the branch not carrying, the merge
not passing. One marble at a time, three speeds by seven lateral positions:

| | entries | reached the lobe | reached the merge | finished |
|---|---|---|---|---|
| blue | 15 | 11 | 11 | 11 |
| orange | 3 | 3 | 3 | **3** |

**PASS: both routes carry marbles to the finish.** The sort is by speed, as the
bank geometry implies: at 36 wu/s all seven entries stay on blue, at 43 and 50
the fast ones ride up the bank onto orange.

### Why the production course still ships one route

With the fork built, a full eight-marble field loses too many marbles to ship.
Over 32 seeds:

| | finish | escape | stuck | blue share | orange share |
|---|---|---|---|---|---|
| `routes="blue"` | 0.805 | 0.023 | 0.172 | 1.00 | — |
| `routes="both"` | **0.293** | 0.488 | 0.219 | 0.363 | 0.637 |

Route *usage* is good — both routes well above section 11's 25% target — and
that is new. Reliability is not: `leg3[80]` takes 61 losses and
`orange_lead[0]` 27, of about 180. The fork sorts the field and then throws a
third of it off the course, and the guard-window arithmetic in
`joins.FORK_GUARD_WINDOW` was derived for the old mouth position and has not
been re-derived for the new one.

So section 32's "both blue and orange routes are physically used" is met in the
controlled test and **not met in a production race**. The advance over V1 is
real and it is not the finish line: V1 could not put a marble on orange at all,
and now the blocker is a measured containment number at one named sample range
rather than an unexplained one.

---

## 4. The corrected benchmark

600 seeds, 4800 racers, 32-second window at 240 Hz, `routes="blue"`. 2800 s of
wall time on seven workers. Everything below is
`docs/validation/sloped_race_v1/reliability_v11.json` and `fairness_v11.json`.

### Reliability

| | V1 (defective course) | V1.1 | |
|---|---|---|---|
| finished | 84.35% | **91.96%** | +7.6 points |
| escaped | 8.33% | **1.12%** | 7.4x better |
| stopped in the machine | 7.31% | 6.92% | about the same |
| all eight finished | 161 of 600 (26.8%) | **324 of 600 (54.0%)** | doubled |

| finishers | 8 | 7 | 6 | 5 | 4 |
|---|---|---|---|---|---|
| races | **324** | 197 | 53 | 21 | 5 |

The escape problem is solved: 53 racers of 4800 leave the course, against 400
in V1, and no race loses more than four marbles where V1 lost a whole field.
Section 14's "zero ordinary track escapes" is not met and 1.12% is a long way
closer to it than 8.33%.

**Section 14's 98-99% finish target is not met, and one site is three quarters
of the gap:**

| site | losses | share of the 384 |
|---|---|---|
| `blue[100..119]` | **285** | 74% |
| `leg2[80..99]` | 48 | 13% |
| `leg1[60..99]` | 43 | 11% |
| everything else | 8 | 2% |

`blue[100]` is the merge again, and it has changed character rather than gone
away: V1 lost 319 marbles there *over the side*, and V1.1 loses 285 there
**stopped**. Opening the sprint's guard rails removed the ledge they were
falling off; the apron still brings a marble to rest. Blue's own tail is not
the cause — it is monotone at −0.043 to −0.063 with no flat spot, checked. This
is the single highest-value thing left on the course: fixing it would take the
finish rate to about 97.8% and the all-eight rate with it.

### Fairness, and it is still not fair

| | V1 | V1.1 |
|---|---|---|
| strongest bay | 2, at 22.17% | 2, at **24.00%** |
| weakest bay | 0, at 2.50% | 0, at **2.67%** |
| ratio | **8.87** | **8.99** |
| Spearman, bay against mean rank | −0.074 | −0.051 |

| bay | win | podium | finish | stuck | rank at 9% | rank at 75% | finish rank |
|---|---|---|---|---|---|---|---|
| 0 | 2.67% | 23.3% | 90.3% | 9.3% | 6.20 | 5.20 | 4.84 |
| 1 | 7.67% | 35.2% | 91.7% | 7.2% | 5.14 | 4.73 | 4.45 |
| 2 | **24.00%** | 51.3% | 94.0% | 4.0% | **2.80** | 3.77 | 3.55 |
| 3 | 11.83% | 34.5% | 92.2% | 6.8% | 4.60 | 4.58 | 4.35 |
| 4 | 17.67% | 40.3% | 91.8% | 6.5% | 3.88 | 4.33 | 4.05 |
| 5 | 11.00% | 33.2% | 90.8% | 8.0% | 4.88 | 4.73 | 4.44 |
| 6 | 17.50% | 48.5% | 93.0% | 6.2% | 3.64 | 3.96 | 3.73 |
| 7 | 7.67% | 33.7% | 91.8% | 7.3% | 4.86 | 4.69 | 4.44 |

**The target was a ratio at or under 2.0 to 2.5 and the measured ratio is
8.99.** It has not moved. §2 is the whole explanation and it is a real finding
rather than an excuse: the bias is made in 1.97 layout units of converging
trough, every static thing added there makes it worse, and the one mechanism
that undoes it works by holding the field up.

Two things in the table are worth reading past the ratio. Finishing is now
close to fair — 90.3% to 94.0%, a 3.7-point band, against V1's 5.2 — so the
bias is about *where* in the pack a marble ends up and not whether it survives.
And the course still regresses what it is handed: the 9% spread of 3.40 places
is 1.43 by three quarters.

### Entertainment

| | V1 | V1.1 |
|---|---|---|
| lead changes a race | 4 to 6 | **4.55** |
| overtakes a race | — | 41.0 |
| winner lock fraction | — | 0.165 mean, 0.149 median |
| winner's worst rank | — | 2.02 |
| final margin | 0.03 to 0.67 s | 0.47 s median, 0.55 mean |
| collisions a race | — | 96.7 |

The winner is not settled until 16.5% of the race remains, the winner has been
as far back as second on average, and the median finish is under half a second
apart. Section 20's warning about over-optimising fairness did not bite,
because fairness was not optimised.

### Two numbers outside budget

`max_travel_per_tick` is 0.668 against a 0.5 budget and the worst penetration
is −0.636. Both belong to marbles that have already left the channel and are
falling — the production seed's own contact check is clean (§6).

---

## 5. The selected seed

**Seed 83**, chosen from 324 all-eight-finisher races by the benchmark's own
score: winner lock 0.436, final margin 0.517 s, 7 lead changes.

    1  marble 0  slot 1   16.317 s
    2  marble 4  slot 0   16.833 s
    3  marble 2  slot 6   16.933 s
    4  marble 3  slot 2   17.467 s
    5  marble 7  slot 3   17.933 s
    6  marble 1  slot 7   18.167 s
    7  marble 5  slot 4   18.433 s
    8  marble 6  slot 5   19.033 s

All eight finish, inside 2.7 seconds, with seven lead changes. It is worth
noting which bays are at the front: the winner starts in **slot 1** and **slot
0 is second** — the two weakest bays in the table above. The seed was picked on
race quality, not on that, and it is a reminder that an 8.99 win ratio over 600
races is a distribution and not a script.

Nothing about the physics was altered to obtain it. The old seed 5 is not
carried over.

---

## 6. Determinism

Seed 83, 20 repeats in one process and 20 more in fresh child processes:

| | |
|---|---|
| in process | 20 runs, **identical** |
| fresh process | 20 runs, **identical** |
| one against the other | **identical** |
| state digest | `bce87242cab81ede5c55e106fe64487b9fb856c0543951e0b8e2879374b934ca` |
| event digest | `1ae4b95b4167a61604af4c93a1cfb8eab50425c8e4a0dce15c4e4da493d68fca` |
| finish order | `[0, 4, 2, 3, 7, 1, 5, 6]` |

Identical state digest, event digest, finish order, route assignment and finish
times across all forty, and the state digest is the one the exported replay
carries. 1168 s of wall time. `docs/validation/sloped_race_v1/determinism_v11.json`.

The replay's own contact check is clean: 1921 frames, worst penetration
**−0.0677** against a 0.25 budget, worst resting gap 0.0522, **no findings**.

---

## 7. The video

`output/sloped_race_v1/real_race_v11.mp4` — 1080x1920, 60 fps, 1245 frames,
20.75 s, h264, **no audio stream**. Rendered from the authoritative replay
only; Godot never calls `stepSimulation`.

Eleven cuts, and the racers-in-frame count for each is what section 25 asks
about:

| cut | seconds | in frame |
|---|---|---|
| establish | 0.00-0.95 | 8/8 |
| start | 0.95-2.72 | 6/8 |
| descent | 2.72-3.72 | 8/8 |
| long | 3.72-4.92 | 5/8 |
| hairpin | 4.92-5.92 | 7/8 |
| straight | 5.92-7.12 | 7/8 |
| obstacle | 7.12-10.10 | 8/8 |
| split | 10.10-11.30 | 5/8 |
| branch | 11.30-13.37 | 3/8 |
| merge | 13.37-15.65 | 5/8 |
| finish | 15.65-20.73 | 7/8 |

No cut is empty and three hold the whole field, which is the thing the V1 video
could not do because the field was not there. `branch` at 3 of 8 is the weakest
and the reason is the course rather than the camera: one route, and a field
that has spread over the lobe by then.

One camera finding stands: at the finish the aim moves 0.463 layout units in a
frame against the fastest racer's 0.377. It is a fraction of a marble diameter
of lead and it is recorded rather than tuned away, because section 24 says
cameras come after the physics and the physics is not finished.

`docs/validation/sloped_race_v1/contact_sheet_v11.png` is the nine section
stills.

---

## 8. Known issues

1. **`blue[100..119]` still takes 285 of the 384 remaining losses**, and they
   are now *stopped* rather than *escaped*. Diagnosed but not fixed. Six
   marbles over 24 seeds came to rest at the same point to two decimals —
   merge-apron frame along **−4.45**, across **−0.59**, speed 0.00 — which is
   2.5 units *upstream* of blue's own exit and 0.4 upstream of the apron's back
   edge, where the apron's height field ends over blue's channel. Rolling and
   spinning friction are both **zero** in the core config, so a marble cannot
   stop on a downslope: this is a geometric trap, and its reproducibility says
   it is one shape rather than a tolerance. Fixing it takes the finish rate
   from 91.96% to about 97.8%. It is the highest-value thing left.
2. **The fork is not production-ready.** Both routes complete in the controlled
   entry test — orange 3 of 3 — but a full field loses a third of itself at
   `leg3[80..99]` (61 of ~180 over 32 seeds) and `orange_lead[0..19]` (27
   more), for a 29.3% finish rate against blue-only's 92.0%. Route *usage* is
   good, 36/64. `joins.FORK_GUARD_WINDOW` and the ridge were derived for the
   old mouth position and have not been re-derived for the new one. The
   production course ships `routes="blue"`.
3. **The start bias is unchanged at 8.99.** Eleven geometries scanned; every
   static one made it worse, and the only mechanism that reduced it did so by
   jamming a fifth of the field. §2 has the diagnosis, which is exact.
4. **`course_machine.gd::_spec_for` cannot find `leg 3`.** A node-name lookup
   with a space in it, pre-existing, falling back to the first run's spec — so
   leg3's *supports* are placed from the launch's clearance table. Cosmetic, in
   the render only, and out of this session's scope.
5. **`sloped.contract` carries two named deviations**, both orange's, both
   with their own budget rather than a widened tolerance. They are against the
   *recorded* course; `course_layout.gd` has been updated to match the physics,
   and `docs/validation/sloped_race_v1/terrain.json` has been regenerated from
   the rebuilt scene - the terrain bench is cut from all seven runs' paths, so
   orange's tail moving it by 0.0015 at one lattice point was a real staleness
   and not a tolerance question.
