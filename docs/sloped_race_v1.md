# The sloped course, raced

The approved shape from `marble-sloped-course-lab` — layout B, ZIG-ZAG
RACEWAY, 237 units of channel over a 37-unit drop, of which 197 are raced —
under real PyBullet
physics at 240 Hz, with eight marbles, an authoritative replay, and a Godot
video whose cameras follow the field.

This document is what the brief's sections 44 and 50 ask for. The geometry
argument is in `docs/sloped_race_v1_junction_finding.md`; the numbers are here.

---

## 1. What the physics course is

`sloped.pathing` is a sample-for-sample port of the GDScript that built the
photographed course: `lab_forms.smooth_path`, `v2_forms.resample`, `curvature`,
`smooth_series`, `auto_bank` and `banked_basis`. `sloped.contract` checks the
port against `docs/validation/sloped_course/physics_layout.json`, which was
written *from the built scene* rather than from the layout table:

| checked | result |
|---|---|
| recorded centreline points | 182 of 182, worst gap **0.00084** layout units |
| recorded lengths, drops, widths, floor offsets, profile scales | all exact |
| recorded bank extremes | all exact |
| recorded module anchors | all exact |
| findings | **0** |

0.00084 is the rounding in Godot's JSON writer. The reconstruction is the
photographed curve, not a curve near it.

**The one run the physics does not take as drawn.** `joins.blue_controls`
enters the blue lobe at its *second* authored control, dropping
(5.20, 10.40, 18.55), so that `blue_lead` arrives 7.90 units from leg 3's exit
instead of 1.115 — room for the 12.8 degrees of turn the join needs at a
radius of 4.26 against the 2.43 required. That is the §7 change recorded in
`docs/sloped_race_v1_junction_finding.md`.

Sample for sample the two curves are 6.73 layout units apart, which sounds
alarming and is a statement about parameterisation: the raced lobe is a
shorter curve, so its 118 samples sit at different arc positions. The quantity
that decides whether the video is honest is the perpendicular distance from
the raced path to the drawn ribbon, and that is **0.064 layout units** — a
ninth of a marble radius — over the whole lobe. The marbles run where the
ribbon is drawn.

**The number that would have invalidated everything downstream:**
`v2_track.SAMPLES` is 132 and `course_machine.gd` line 103 passes **118**. At
132 the reconstruction misses the recorded centreline by up to 0.31 layout
units — half a marble diameter and a half — worst exactly at the hairpins,
where the samples are furthest apart. Every *length* agrees at both counts, so
a length check alone passes a course whose hairpins are a marble's width from
where they were drawn.

### The collider

Traced across the inner surface `v2_track.channel_section` authors, not a
straight wall at the channel edge:

```
guard top     1.002, 0.540   ─┐
guard base    1.002, 0.280    │  acrylic rail: the real containment
lip inner     1.000, 0.265   ─┤
              0.985, 0.180    │  the rolled lip's four authored points
              0.970, 0.080    │
              0.950, -0.010  ─┘
cradle edge   0.940, -0.049  ─┐
              0.705, -0.145   │  a circular arc of radius 2.20, five points
              0.470, -0.210   │  per half, which is what the asset uses
              0.235, -0.247   │
centreline    0.000, -0.260  ─┘
```

A collider that stands a straight wall at |across| = 0.94 holds a marble 0.06
layout units — a tenth of a diameter — clear of the surface it appears to lean
on. Containment is 0.80 layout units from the cradle's lowest point to the
guard's top: **1.404 simulation units, 1.40 marble diameters.**

| | vertices | triangles | chunks | mesh findings |
|---|---|---|---|---|
| per channel run | 2,478 | 4,680 | 1 | 0 |
| the course as raced | 19,285 | 33,986 | 12 bodies | 0 |
| the course with both lobes | 22,797 | 40,566 | 15 bodies | 0 |

118 samples is also the right resolution and not only the photographed one:
the worst per-facet sagitta over the whole course is inside the core's 4%-of-a-
radius budget, and the core's own finding is that a *finer* collider dissipates
more, because a rigid sphere loses energy at every triangle edge.

### The one scale

`marble3d.units` says a marble is 0.5 world units, because Bullet's fixed
tolerances are absolute lengths and a machine authored fifty times below the
scale the engine expects does not survive it. The approved course says 0.285,
because that is what its channel, bays, blades and finish lanes were authored
around. `sloped.scale` resolves it with one factor:

    LAYOUT_TO_SIM = 0.5 / 0.285 = 1.754386

applied on the way in. The replay stays in simulation units — it is the
physics' own record — and Godot converts once, as a uniform scale on the node
the marbles are parented to, read from the replay's own `units.render_scale`. A
uniform scale on a parent scales its children's translations *and* their radii,
so one number puts an 0.5-unit marble at the right size and the right place.

Simulating at 0.285 instead would mean re-deriving six measured absolutes — the
0.001 mesh margin, the 0.02 contact-breaking threshold, the swept-sphere
radius, the travel budget, the sagitta limit, the triangle-edge bound — from a
similarity argument rather than applying the argument once.

---

## 2. The nine things that stopped it, and what each cost

Every correction is local to one station, and every one was found by
measurement. The failure mode of a shape composed for a camera is a shape that
looks right and does not work.

Corrections 1 to 8 were measured before 9, so the counts in their "measured
failure" column describe a course whose gate was rotated and whose field
therefore arrived at each station as a trickle rather than a pack. Each of the
eight is a geometric defect and each fix is justified by the geometry, not by
those counts — but the counts are not comparable with §3's, and where one of
them is a *tuned* value rather than a derived one it is flagged below.

| # | station | as drawn | measured failure | correction |
|---|---|---|---|---|
| 1 | start | lane fins 0.11 across a 0.63 bay pitch — 0.52 clear against a 0.57 racer | all eight marbles in a vice, 0.019 units of overlap each side; the field reached 0.1 wu/s in three seconds and stayed there | fins become floor ridges, and stop at half the fan, because the drawn ones converge to a 0.24 pitch and crush what they guide |
| 2 | start | trough dish 0.16 deep across 1.02; channel cradle 0.211 across 0.94 | a step of up to 0.09 at the seam; the last marble of the queue stopped on it in **every** seed | the trough's section blends into the channel's over the last third of the fan |
| 3 | mixer | pins built at their full 0.56 length | five pins across a 1.88 channel leave 0.25 gaps; six marbles piled against them in four seconds | 0.07 above the cradle — see the scan below |
| 4 | obstacle | blades reach 1.39 from the shaft against a 0.94 half width, sweeping y = −0.37 to +0.41 against a cradle at −0.26 | blades pass through both the floor and the guards | blades sweep inside the channel, above the cradle at the tip radius; neighbouring wheels turn opposite ways |
| 5 | fork | — | six configurations, none of which works — see §4 | one route |
| 6 | branch leads | 0.82 profile scale | a 0.82 profile is 0.82 as *deep*: 1.16 of containment does not catch a marble thrown across the fork at 43 wu/s | hero scale, with the *width* tapering to the lobe's 0.82 |
| 7 | branch leads | carried at the Hermite's 48 samples | 30 degrees of roll in one layout unit at the seam; 15 of 24 stopped at leg3's exit | the course's own 0.289 spacing — which is also the sagitta the core is calibrated at |
| 8 | merge | apron laid out in the sprint's frame *and* subtracting its gradient | the apron came out 0.74 simulation units — three quarters of a diameter — **above** blue's channel floor; 23 of 48 stopped dead against that step | interpolates between the sprint's contact point and blue's, so it is flush with both by construction |
| 9 | start gate | eight paddles, each given a bay's width on its local X | `basis_from_forward_up` puts the direction it is handed on **+X**, and the gate hands it the direction of travel — so every paddle was a 0.9-long, 0.16-wide blade lying *down the middle of its bay* rather than across it. All eight marbles were seeded 0.34 units inside their own paddle, with a contact normal along the flow | the extents become (thin, height, bay width). See below: this one changed the race |

### The gate that did not gate

Correction 9 arrived last and mattered most, and it is worth separating from
the other eight because it was not found by watching marbles get stuck. It was
found by asking why one number would not go away.

The core reports a worst penetration per race. Across 600 races it was
**−0.3520**; on the seed picked out of those 600 it was **−0.3520**; on a
0.05-second run of that seed, before anything had moved faster than 0.71 world
units a second, it was **−0.3520**. A constant is not a collision — and being
the same in all 600 races is what made it findable, not being the largest.
Traced: it
appeared on tick 1 against the start module and decayed smoothly to −0.014 by
tick 40, the signature of Bullet pushing a body out of a static overlap, and
its contact normal was purely horizontal — along the flow, not up out of the
cradle.

The paddles were rotated ninety degrees. Which means the eight-marble field was
not being *held* at all: it left the grid because the fan is downhill, and the
gate lifted at its release time onto nothing. With the axes right, the gate
does what the drawing says — the field stands still until 0.3 s, the paddles
lift over 0.16 s, and at 0.75 s the eight are moving at a mean of 5.14 and a
maximum of 5.23 world units a second, which is a pack leaving together rather
than a queue trickling away.

The seeded overlap went from **−0.352 to −0.0053**, and that residue is the
resting contact of a marble on the cradle and the lane ridges beside it.

This invalidated the first 600-race benchmark, the seed chosen from it, the
nine stills and the video, all of which were re-made. That is the cost of
finding it late; the alternative was shipping a race whose start does not work
and whose deepest measured penetration is a third of a diameter of our own
geometry.

### The mixer scan

The mixer has two jobs and the second one was a surprise.

| pin height | finished | escaped | jammed |
|---|---|---|---|
| 0.20 (as drawn) | 16 of 32 | 10 | — |
| 0.10 | 26 of 32 | 3 | — |
| 0.10 (full course) | 14 of 24 | 8 | 2 |
| **0.07** | **22 of 24** | **2** | **0** |
| 0.05 | 13 of 24 | 1 | **10** |

A 0.20 stud stands 0.70 of a marble radius, so a marble at 25 wu/s meets it
below its own equator and is levered up over a wall 1.40 tall. And 0.05 is
worse than 0.07 for the opposite reason: nine of its ten jams are at the fork's
nose. **A mixer that deflects too little leaves the field bunched, and a
bunched field cannot take the split.** Spacing the pack is the mixer's second
job.

This scan is the tuned value the note above warns about, and it is the one most
exposed to correction 9: what the mixer has to do depends on how bunched the
field arrives, and un-rotating the gate is precisely a change to that. It was
not re-scanned, and the argument for leaving it is in §3's loss sites rather
than in a repeated scan — with the gate fixed, the launch's last fifth, which
is where the mixer stands, accounts for **71 of 747** losses across 600 races,
and the course finishes 84.35%. A pin height that had stopped working after the
field started arriving as a pack would not look like that. It remains a fitted
constant (§9 item 7).

---

## 3. Reliability

600 seeds, eight marbles each — **4800 racers** — every one simulated for a
30-second window at 240 Hz. 2451 s of wall time on seven workers, 0.245 seeds a
second. Everything below is from
`docs/validation/sloped_race_v1/fairness.json`.

| | |
|---|---|
| finished | **84.35%** |
| escaped | 8.33% |
| stopped in the machine | 7.31% |
| races where all eight finished | **161 of 600** (26.8%) |

| finishers | 8 | 7 | 6 | 5 | 4 | 3 | 0 |
|---|---|---|---|---|---|---|---|
| races | 161 | 219 | 149 | 58 | 8 | 4 | 1 |

The modal race loses one marble. A quarter of them lose none, and one seed in
600 lost the whole field.

### Where they are lost

747 losses, and they are not spread along the course — two junctions take
two-thirds of them.

| site | lost | what is there |
|---|---|---|
| `blue[100]` | **319** | blue's exit into the merge catch |
| `leg1[0]` | **193** | the launch → leg 1 seam, the first corner after the drop |
| `launch[100]` | 44 | the launch's own exit |
| `leg1[80]` | 39 | leg 1's tail |
| `leg1[20]` | 37 | leg 1's entry |
| `leg2[80]` | 34 | leg 2's tail, at the obstacle |
| `launch[80]` | 27 | |
| `leg1[60]` | 20 | |

Both dominant sites are places where something wide narrows and turns at speed,
and both survived a correction already: the merge apron was rebuilt
(correction 8) and the seam geometry closed. What is left is not a step to be
removed but the containment being 1.40 diameters where the arrival is fast and
off-axis.

### Fairness, and it is not fair

| | |
|---|---|
| expected win rate per bay | 12.50% |
| strongest bay | **2, at 22.17%** |
| weakest bay | **0, at 2.50%** |
| ratio | **8.87** |
| Spearman, bay index against mean rank | −0.074 at every checkpoint |

| bay | wins | podium | finished | stopped | mean finish rank | rank at 9% | rank at 75% |
|---|---|---|---|---|---|---|---|
| 0 | 2.50% | 19.8% | 84.0% | 9.2% | 4.79 | 6.35 | 5.19 |
| 1 | 6.17% | 34.8% | 84.5% | 8.7% | 4.22 | 5.12 | 4.69 |
| 2 | **22.17%** | 48.3% | 84.7% | 5.5% | 3.30 | **2.74** | 3.92 |
| 3 | 16.33% | 37.8% | 86.5% | 6.5% | 3.84 | 4.51 | 4.36 |
| 4 | 18.33% | 42.7% | 83.2% | 6.8% | 3.64 | 3.76 | 4.27 |
| 5 | 9.83% | 31.2% | 82.8% | 9.2% | 4.31 | 5.04 | 4.85 |
| 6 | 17.67% | **49.5%** | 82.0% | 6.7% | 3.33 | 3.62 | 4.08 |
| 7 | 6.83% | 35.3% | 87.2% | 6.0% | 4.22 | 4.87 | 4.66 |

Three things are worth reading off this rather than just the ratio.

**The bias is positional, not a mirror.** The inner bays — 2, 3, 4, 6 — take
three quarters of the wins between them and the outer pair, 0 and 7, take
9.3%. Eight bays at a 0.63 pitch converge into one 3.3-diameter channel, and
the inner bays have the shortest and straightest path into it. The seeded
resting heights are symmetric across the fan to the last decimal, so this is
the *convergence* rather than the placement.

**It is decided early and then partly undone.** At the 9% checkpoint the mean
ranks span 2.74 to 6.35 — a spread of 3.6 places. By the three-quarter mark
they span 3.92 to 5.19, a spread of 1.27. The course spends its length
regressing the order it was handed, which is why the finish is close (§5) even
though the start is not fair. The Spearman is the same at every checkpoint
because it ranks the eight bays against each other and that ranking does not
change; only its spread does.

**Finishing is fair even where winning is not.** Finish rates sit between 82.0%
and 87.2% — a 5-point band on a 12.5-point expectation — and the weakest bay
for winning, bay 0 at 2.50%, is mid-table for finishing at 84.0%. The bias is
about where in the pack a marble ends up, not about whether it survives.

**Correction 9 improved it by a third and did not fix it.** Before the gate was
un-rotated, the same 600-seed measurement gave a ratio of **13.2**, a strongest
bay of 33.0% and a Spearman of −0.119. A field released as a pack is fairer
than a field trickling off a fan, but the fan is still the fan.

### Two penetration numbers, and what each covers

| measure | worst | budget | what it looks at |
|---|---|---|---|
| the core's, over 600 races | −0.3926 | — | every contact, including the obstacle's kinematic blades |
| the core's, production seed | −0.2805 | — | as above |
| `sloped.contact`, production seed | **−0.0533** | 0.25 | a marble against its channel's own cross-section |

They disagree because they measure different things, and the disagreement is
localised: the core's worst on the production seed is marble 4 against an
**obstacle blade** at 9.771 s. A blade is kinematic — it does not yield — so an
overlap with it can only be resolved by moving the marble, and a marble with
the cradle behind it has nowhere to go. That is a property of driving a paddle
wheel through a channel 3.3 diameters wide, not a defect in the channel: the
same marble is 0.053 into the channel, a fifth of the budget.

The travel budget is exceeded — 0.7290 against 0.5 — and §9 item 4 shows that
belongs to marbles already out of the race. The production seed's own worst is
**0.2827**, inside it.


---

## 4. The split: measured six ways, and blocked

The two branch lobes diverge at **56 degrees** from a common point, so a fork
between them has to split a 3.3-diameter channel into two inside the 3.4 layout
units between leg3's exit and the branch mouths, while eight marbles arrive at
43 wu/s.

| divider | guard window | finished | lost at the fork |
|---|---|---|---|
| straight blade on leg3's tangent | +8 to +22 | — | 13 of 24 |
| blade on the bisector | +8 to +22 | — | 4 dead, the rest queued |
| ridge, foot ≤ half width | +8 to +22 | 68% | 40 of 256 |
| ridge, foot ≤ 0.55 of it | +7 to +16 | 57% | 73 of 256 |
| ridge spanning the cradle gap | +5 to +14 | 41% | 14 of 32 |
| ridge in the gap, mouth flared | 0 to +14 | 0% | 21 of 32 |
| **no fork at all** | shut | **85%** | **0 of 48** |

**These six rows were measured before correction 9.** The gate was rotated for
all of them, so the field arriving at the fork was a queue trickling off the
fan rather than a released pack, and the finish percentages in the last column
are not comparable with §3's. What does not depend on the gate is the geometric
argument below it — the divergence angle, the room available and the radius a
141-degree turn at 41 world units a second needs — and that argument is the one
carrying the conclusion. The rows are kept because each names a distinct
mechanical failure, and those mechanisms are unchanged.

Each failure had a different cause and each is recorded where it was fixed, in
`sloped.stations.ForkRidge` and `sloped.joins.FORK_GUARD_WINDOW`. The pattern
across all six is one trade:

* a divider big enough to sort the field is big enough to queue it;
* a guard open enough to let a marble cross is open enough to lose one;
* a guard shut enough to hold the field is shut enough that orange is
  unreachable.

**The route attribution was wrong for the first four rows and correcting it
changed what they mean.** It fixed a marble's route on its first contact with a
branch collider — and the two channels *overlap* at the fork, where they are the
same channel — so it credited orange with 125 of 225 marbles and then reported
ten of them lost on leg3's tail, which is blue's route. Route now comes from
where a marble is *located*, past the samples the two still share floor.
Corrected: **no configuration ever put a marble on the orange lobe and got it
to the finish.**

So the course ships with one route. `sloped_course(routes="both")` still builds
the fork — the shapes matter as much as the numbers to whoever looks at this
next — and its 5.7% route-length difference and its own seam and radius checks
are all clean. What is missing is not a check; it is 3.4 units of room.

### What the brief's split questions come to

* **entry counts** — 100% blue, 0% orange, because orange is not reachable.
* **travel time, collision count, exit rank change, failure rate per route** —
  measurable for one route only, and reported in §3 as the course's own.
* **structural dominance** — there is no second route to dominate.

Section 4 of the stop condition is met in the sense that the split bias was
measured, six times. It is not met in the sense that there is a bias to report.

---

## 5. Race quality

Section 30's list, measured across the same 600 races.

| | mean | median |
|---|---|---|
| lead changes | **5.30** | |
| overtakes | 41.8 | |
| marble-on-marble collisions | 72.5 | |
| finishing margin, first to second | **0.546 s** | 0.483 s |
| how late the winner's lead was settled | 0.167 of the window | 0.135 |
| the winner's worst position | **2.56** | |
| top speed | 118.7 wu/s | |
| race time, gate to line | 16.60 s | 16.45 s |
| rank change over the second half | +0.061 | |

Read together: a typical race changes hands five times, is decided by half a
second, and its winner was second at some point. The mean rank change over the
second half being +0.061 — essentially zero — is the same fact the fairness
checkpoints showed from the other side: the order keeps moving, but it moves
symmetrically rather than drifting one way.

The route the marbles actually travel is **197.12 layout units** long, 345.83
in simulation units, over a 37-unit drop. The course carries 236.9 units of
channel in total; the difference is the orange lobe, which is built and not
raced (§4).


---

## 6. The selected seed

**Seed 5.** It is the top of a shortlist of 12 drawn from the **161** races in
which all eight marbles finished with none escaped and none jammed, and it wins
that shortlist by a clear margin: 3.6899 against 3.3380 for the next.

The score is five terms, each visible so the pick can be argued with rather
than taken on trust:

| term | value | what it measures |
|---|---|---|
| comeback | **1.000** | the winner was as low as **6th** |
| turnover | **1.000** | 8 lead changes |
| margin | 0.892 | 0.217 s between first and second |
| lock | 0.798 | the lead was not settled until **14.37 s** |
| split | 0.000 | one route — unreachable, see §4 |

| place | marble | bay | time |
|---|---|---|---|
| 1 | 6 | 4 | 15.783 s |
| 2 | 7 | 1 | 16.000 s |
| 3 | 5 | 3 | 16.233 s |
| 4 | 3 | 7 | 16.317 s |
| 5 | 2 | 2 | 17.033 s |
| 6 | 0 | 6 | 17.367 s |
| 7 | 1 | 5 | 17.617 s |
| 8 | 4 | 0 | 18.533 s |

Four marbles inside six tenths of a second, the winner from sixth, and the
finishing bays reading 4, 1, 3, 7, 2, 6, 5, 0 — not the bay order, which is the
point. 43 overtakes, 83 collisions, top speed 67.9 wu/s, worst travel per tick
0.283 against a budget of 0.5.

    replay   output/sloped_race_v1/race_5.json   (6 MB; output/ is not tracked)
    digest   38936883898c8a45951fa92fcdf14338d189809bada43104ba16a4e7b9305f9d
    events   0cbc106419c22cddd275c69a26933e5e913adfd3ee5c2f92df3b21cb0780389b

Contact validation (`--stage check`,
`docs/validation/sloped_race_v1/contact_5.json`): **no findings** over
1801 frames and 6996 channel samples, worst penetration −0.0533 against a
budget of 0.25 and worst resting gap 0.0536 against 0.06. A further 7395
samples are on stations, where a cross-section comparison does not apply —
§9 item 5.


---

## 7. Determinism

`tools/sloped_determinism.py --seed 5 --duration 30 --repeats 20`, 690 s of
wall time, written to `docs/validation/sloped_race_v1/determinism.json`.

| | runs | result |
|---|---|---|
| repeated in one process | 20 | **identical** |
| repeated in fresh child processes | 20 | **identical** |
| one set against the other | — | **identical** |

Identical means every one of these agreed, not just the finishing order:
the frame digest, the event digest, the simulated seconds, the frame count, the
finishing order, every finishing time, every marble's route and every marble's
start bay.

    digest   38936883898c8a45951fa92fcdf14338d189809bada43104ba16a4e7b9305f9d
    events   0cbc106419c22cddd275c69a26933e5e913adfd3ee5c2f92df3b21cb0780389b
    order    [6, 7, 5, 3, 2, 0, 1, 4]

That digest is the same one `race_5.json` carries, so the replay the video was
rendered from is bit-for-bit the race this test reproduced forty times.

The fresh-process half of the test is the half that matters. Twenty repeats
inside one interpreter share a warm mesh cache, one PyBullet client's
allocation history and one process's floating-point environment; twenty fresh
children share none of that, and they still agree.

**Cross-machine determinism is not tested** — one machine was available. The
record includes what a second machine's report would be diffed against:

    platform     Windows-11-10.0.26200-SP0
    machine      AMD64
    processor    Intel64 Family 6 Model 154 Stepping 3, GenuineIntel
    python       3.13.0
    pybullet_api 202010061

Bullet is not guaranteed bit-identical across CPU architectures, compiler
builds or library versions, so this is a claim about one build on one machine
and §9 item 6 says so.

---

## 8. The video and the cameras

The cameras are solved in Python, in layout units, one position and one aim
per output frame per cut, and written to `cameras_<seed>.json` — the production one is
committed as `docs/validation/sloped_race_v1/cameras_5.json`. Godot sets the
camera from that table and does nothing else to it: no look-at in the scene, no
smoothing in the scene, and — section 30 — no `stepSimulation` anywhere in the
render path. The marbles come from the replay's transforms and the camera from
the track, so a frame is reproducible from two files.

Eleven cuts, in course order. `establish` is the only one aimed at a fixed
node, and it is capped under a second by section 39.

| cut | station | fov | extent | elev | bearing | target |
|---|---|---|---|---|---|---|
| establish | grid | 30 | 110 | 30 | 200 | node `hero` |
| start | launched | 34 | 9.5 | 16 | 28 | node `start` |
| descent | mixed | 36 | 20 | 24 | 160 | pack |
| long | leg1_apex | 36 | 20 | 18 | 22 | pack |
| hairpin | leg2_start | 34 | 24 | 34 | 20 | pack |
| straight | obstacle | 36 | 14 | 16 | 30 | pack |
| obstacle | sweep | 32 | 8 | 15 | 44 | pack |
| split | promontory | 34 | 16 | 26 | 8 | pack |
| branch | branch_out | 36 | 19 | 22 | 152 | pack |
| merge | sprint | 34 | 15 | 24 | 6 | pack |
| finish | line | 36 | 15 | 20 | 155 | pair |

### Three things the frames taught the arithmetic

**The aim was not on the course.** A pack aim was the centroid of the chosen
racers' positions. At leg 1's apex the course turns back on itself, so
averaging a field spread across both legs of the turn lands the average
*between* them — inside the hillside. The terrain check reported it as a sight
line the ground crossed by 3.51 layout units at 46 degrees of elevation, the
ceiling, with no bearing able to fix it; measured at that frame, the aim sat at
y = 20.76 under a ground height of 24.27, and the port agrees with the scene's
own dump to 0.0025 at the four nearest grid points, so the ground really was
above the aim. The aim is now the course's own point at the pack's mean
progress, which is on the racing line by construction. Nothing was
unreachable after that: on the replay the fault was found on, every cut cleared
the ground by 0.72 to 3.32 units with two degrees of lift on one cut and none
on the other ten, and the distance from each aim to its nearest racer fell to
between 0.5 and 1.7 layout units. This also accounts for `long` and
`hairpin`, the two turns, having been the two weakest frames of the first
full-resolution pass: one fault, not two accidents of framing.

**A marble is inside a wall.** A racer sits in a cradle 1.4 marble diameters
below the top of the channel's outer acrylic guard, so a camera looking
*across* a leg has that guard between it and the field at any elevation —
raising it only changes how much wall the marbles are seen through. `straight`
proved it: the frustum arithmetic counted seven racers in frame and the render
showed none, then showed them dimmed and smeared through the acrylic when the
camera came closer. Every bearing is now within 45 degrees of along-track, or
past 150 and looking back along it. No cut kept a side-on bearing.

**The subject has to be chosen once.** Membership of a pack was re-decided
every frame, and a set that gains and loses members has a centroid that can
move faster than anything in it: at the fork the aim travelled 1.8 times as
fast as the quickest marble on the course. The subject is now fixed at each
cut's midpoint, which bounds the aim's speed by its own members' by
construction. Across the eleven cuts the aim now moves at 0.31 to 0.93 of the
fastest racer in its own shot.

### What is checked before anything is rendered

`sloped.cameras.check_track` and `frame_report` run on the solved track and the
replay together:

* no cut shorter than a third of a second, and the cuts tile the clip with no
  gap or overlap — the bounds are clamped to the replay, which is what stopped
  a short race producing a finish cut of **−1.500 s**;
* no camera below its own aim;
* no aim moving faster than the fastest racer in its own cut — the first
  version of this test used a fixed diameter per frame and was measuring the
  wrong quantity, since a field descending at 24 layout units a second covers
  most of a diameter per frame legitimately;
* section 37's clearance: the sight line is walked against the ported terrain
  and the elevation raised two degrees at a time until the ground is a marble
  diameter clear, up to a 46-degree ceiling — the ceiling exists because
  section 34 forbids a fixed tower;
* at least two racers inside the frustum, and the nearest at least 24 pixels
  across in the delivered 1080×1920 frame. This one exists because the checks
  above all passed on a cut whose nearest racer was ten units off the aim: none
  of them asked whether the marbles could be seen. It cannot see occlusion,
  which is why `straight` needed a render as well.

Findings on the production track: **none**. Per cut, at its own midpoint,
between 2 and 8 of the eight racers are inside the frustum and the nearest is
between 45 and 155 pixels across; the two turns are the thin ones, at 2 and 5.
Two cuts needed lift — `descent` 12 degrees and `branch` 4 — and the other nine
cleared the ground where they stood.

### The video

`output/sloped_race_v1/real_race.mp4` — at the path section 41 asks for, and
not committed, because this repository has ignored `output/` and `*.mp4` since
before this branch. Probed rather than asserted:

    h264, yuv420p, 1080x1920, 60/1 fps, 1215 frames, 20.25 s, 30.1 MiB
    one stream, index 0, video: no audio track

1215 frames at 60 fps is the camera track's own span, and the camera track runs
from the gate to the last crossing at 18.533 s plus the finish cut's 1.7 s
hold. Rendering took 408 s at 336 ms a frame.

The clip is as long as the *race*: from the gate to the last crossing plus the
finish cut's hold. The renderer on its own uses the replay's duration, and the
replay is as long as the simulation window it was asked for — which spent nine
and a half seconds of the first encode on a parked field under a camera that
had run out of cuts. Nothing is sped up, no frame between the gate and the last
crossing is dropped, and gravity is untouched; what is cut is the simulation
continuing after the race is over.

Rendering is a `SubViewport` at the true output size, with a fixed warm-up
count and a clock that is the output frame index rather than wall time, so a
render that crawls and one that flies produce identical images. That is the
only reason a still can be trusted to be a frame of the clip rather than a
picture near it — each still is taken at its own cut's midpoint.


---

## 9. Known limitations

Ordered by how much they would matter to someone building on this.

**1. One route.** The orange lobe is geometry the physics does not use. Entry
share is 100% blue, so every split question in the brief that needs two
populations is unanswerable here — see §4. The course is `routes="blue"`; the
forked build still assembles, still passes its own seam and radius checks, and
still has no way through.

**2. The start is not fair.** The measurement is in §3 and it is the largest
open problem in this deliverable. The bias is set by the time the field is a
tenth of the way down and it is a property of the drawn fan — eight bays at a
0.63 pitch converging into one 3.3-diameter channel — not of the physics
config. Correction 9 changed it (the field now arrives as a pack, which is a
different collision problem from a queue) but did not remove it.

**3. Not every marble finishes.** The rate and the sites are in §3. The two
dominant loss sites are structural rather than random, and both are junctions
where a wide thing narrows.

**4. The travel budget is exceeded, and only by marbles that are already out.**
The core's budget is 0.5 simulation units in a 240 Hz tick — 120 world units a
second — and a marble that leaves the channel falls the whole 60-odd-unit drop
and arrives at about 172. Measured across eight seeds: the two that lost nobody
peaked at 69.9 and 66.7 wu/s, both inside the budget; every seed that lost a
marble exceeded it. `tests/test_sloped_race.py` asserts the conditional form —
inside the budget when nothing is lost, and no *finisher* over it otherwise —
rather than the unconditional claim, which is false.

**5. Contact validation covers the channels, not the stations.** The checker
compares a marble to its channel's cross-section, which is a plane, so it skips
any sample more than one and a half half-steps along-track from the sample it
would be measured against. Inside a run that never excludes anything; at a
station — the start fan, the mixer housing, the merge apron, the finish deck —
it excludes everything, and those samples are counted as off-channel. So a
defect in a station's own floor would not be caught by `--stage check`. It was
caught, eight times, by marbles stopping.

**6. Determinism is verified on one machine.** Twenty repeats in one process
and twenty in fresh ones, identical (§7). Bullet is not bit-identical across
CPU architectures, compiler builds or PyBullet versions, and nothing here
tests that; `determinism.json` records the interpreter, platform and PyBullet
API version the run was made on so a future mismatch can be attributed.

**7. The mixer pin height is tuned, not derived.** 0.07 came from a scan
(§2) with a clear optimum on either side, but it is a fitted constant and a
change to marble friction or restitution would move it.

**8. The terrain port is verified on a 7-unit grid.** 396 points from the
running scene agree to **1.7e-5**, and the analytic form is transcribed
function for function, so features between grid points follow from the code
rather than from measurement. It is used only to place cameras, never for
physics — the ground is not a collider.

That figure required cutting the bench from the *drawn* layout rather than
from the raced build, which is what the scene does. Cutting from the raced runs
— whose blue lobe is re-parameterised, see §1 — put the port 0.021 units out.
Rebuilding the production camera track after the correction changed it by
0.000000, so 0.021 never mattered here; it is fixed so that "the port is
exact" needs no footnote.

**9. Section 47's list is untouched.** No audio, no flags, no HUD, no
procedural generator, no camera director, no new modules, no macro redesign,
nothing merged to `main`, nothing deleted. `docs/validation/sloped_course/` and
the layout branch's scenes are unmodified; this branch adds `sloped/`,
`tools/sloped_*`, two Godot scripts, one scene and the tests.

