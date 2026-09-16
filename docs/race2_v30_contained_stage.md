# V30: a contained stage built from the camera outward

**Branch** `v30-contained-stage-v2`, from `origin/v29-switchyard-contained-integration` at `519bc9f`.
**Scope** environment architecture only. No physics, no camera, no course, no racer.

---

## 1. What V29 found, and what it actually meant

V29 put SWITCHYARD and camera A inside V27.2's contained hall and measured the
result. The film came out **64.89% nothing-drawn**, the final sprint **90.8%
black**, and the three warm practicals the hall authors appeared in **0.000%**
of it.

V29's own diagnosis was right as far as it went: *the hall is a rim, not a
room*. Its deck is an annulus with an 88-unit inner radius and SWITCHYARD's
plan reach is 27.06, so the camera spent the film looking down the hole where
the floor should have been.

**What that diagnosis is missing is the general rule**, and the general rule is
what this pass is built on:

> V27's hall was designed in world space and then asked whether the camera
> happened to see it. Every one of its failures is an instance of that: the
> deck starts beyond where the lens looks, the walls stand beyond where the
> lens looks, the bays are sited on another race's node names, and the
> practicals face a direction the lens never points in.

So V30 does not start with a room. It starts with `tools/race2_v30_envelope.py`,
which reads the locked camera track and the locked course geometry and answers
one question - *where do this lens's rays go* - before any geometry exists.

---

## 2. Design principles

1. **The film is the product; the room is supporting geometry.** Every
   dimension in the three profiles is derived from the camera envelope, and
   `tools/race2_v30_stage.py report` re-measures the envelope and complains if
   the film has moved under the design.
2. **Measure before building, and measure the built thing again.** The
   envelope decides the architecture; the marker render decides whether the
   architecture is in the picture.
3. **Anything at 0.000% coverage is removed or justified.** Not "subtle" -
   waste.
4. **The camera is the client and it is locked.** Where a frame looked wrong,
   the environment changed.

---

## 3. The camera A visible envelope

`python tools/race2_v30_envelope.py` — full report in
`docs/validation/race2/v30_stage/envelope.json`.

| | value |
|---|---|
| frames sampled | 385 (every 3rd of 1149) |
| course plan reach | **27.06** |
| course plan span | 26.60 (x) × 48.00 (z) |
| course section | y −0.60 … 36.00 |
| eye height | 9.47 … 47.00 |
| eye plan radius | 1.40 … **45.68** |
| aim elevation | −58.98 … −26.21 |
| **frame top elevation** | −41.30 … **−9.10** |
| centre ray lands at r | 7.43 … **80.87** |
| nearest ground hit | **14.34** |
| centre rays that never come down | **0** |

Four facts fall straight out of that table and between them they design the
stage.

**a. Nothing above the lens is ever seen.** The frame top never rises above
−9.10°. There is no ceiling in any concept, and there is no upper storey. This
is not restraint, it is arithmetic.

**b. Every centre ray lands inside r = 80.87.** V29's deck *begins* at 88.0.
That single comparison is the whole failure, and it needed no render.

**c. The camera travels to r = 45.68.** A closed wall inside that has the lens
standing outside its own room. The sizing sweep confirms it: at r = 40, 19 of
the sampled frames have the eye outside the ring.

**d. The film looks down a 138° arc and never leaves it.** Measured two
independent ways:

- the centre ray's compass bearing over all 1149 frames is **82.3° … 220.8°**;
- at the wall radius, **13 of 24 sectors carry no wall pixel at all**, and four
  sectors (135°, 150°, 195°, 210°) carry **82%** of them.

A rotationally symmetric drum is therefore more than half waste *by
construction*, and this is the measurement behind every "no drum" decision
below.

### 3.1 The sizing sweep

135 rays per frame against a floor disc and an upright wall at each candidate
radius:

| radius | floor | wall | **void** | wall top needed | nearest wall to lens | frames with eye outside |
|---|---|---|---|---|---|---|
| 40 | 41.3% | 58.7% | 0.00% | 26.8 | 2.4 | **19** |
| 50 | 69.4% | 30.6% | 0.00% | 25.7 | 41.9 | 0 |
| 60 | 76.6% | 23.4% | 0.00% | 23.4 | 52.5 | 0 |
| **64** | **78.6%** | **21.4%** | **0.00%** | **22.6** | **57.7** | **0** |
| 80 | 86.2% | 13.8% | 0.00% | 18.9 | 73.6 | 0 |
| 120 | 95.1% | 4.9% | 0.00% | 11.4 | 115.9 | 0 |

**Containment is geometrically easy once there is a floor.** Void is 0.00% at
every radius from 50 up. The V29 failure was never the wall radius - its inner
pylon ring stood at 64.0, which this sweep says is about right. It was that
nothing stood between the course and it.

### 3.2 The number that decided the final sprint

The sweep per shot is where the architecture is actually decided, because the
film is not one framing:

| radius | `release` wall | `upper` wall | `middle` wall | **`run_in` wall** |
|---|---|---|---|---|
| 50 | 76.8% | 51.4% | 15.1% | **1.3%** |
| 64 | 54.0% | 36.5% | 8.9% | **0.4%** |
| 80 | 37.2% | 24.7% | 3.6% | **0.0%** |

**The final sprint is 99.6% floor.** The shot the brief cares most about - 6.47
seconds, one continuous take, the one V29 lost at 90.8% black - contains almost
no wall at any radius. Its background is the floor and nothing else.

That is why **the wall radius is 64**: it is the 95th-percentile corner radius
of the final sprint's own rays (64.11), so the wall terminates the floor exactly
where the money shot's frame edge lands.

### 3.3 The final sprint has no background at all

This is the hardest finding in the pass and it changed the plan. Where the
*top* of the final-sprint frame lands on the floor:

| t | top-left (x, z, r) | top-right (x, z, r) | clearance from the racing line |
|---|---|---|---|
| 13.40 | (20.7, −36.3, 41.7) | (42.4, −20.1, 46.9) | 16.1 |
| 15.60 | (−30.8, −6.4, 31.4) | (−10.5, −16.0, 19.1) | 1.9 |
| 17.60 | (−18.2, 8.6, 20.2) | (−6.4, 10.3, 12.1) | 4.1 |
| 19.10 | (−13.4, 6.9, 15.1) | (−0.3, 10.8, 10.8) | **0.8** |

From about t = 15 onward the top of the frame is landing **0.8 to 4.1 units
from the racing line**. There is no far field. Architecture "behind the racers"
in the final sprint would be architecture *on the track*.

**So the brief's Part Q cannot be answered with scenery, and V30 does not try.**
It is answered with a floor good enough to be the background: rhythm, a second
value, warm inlays placed inside the sprint's own measured footprint, and the
machine's own structure as the only vertical. The numbers say it worked - 0.04%
near-black against V29's 94.02% - but the honest statement of what changed is
"the shot now has a floor", not "the shot now has a set".

### 3.4 Parallax, decided by the radii

Image speed is `v / d` radians per second, so a stage's parallax is fixed the
moment its distances are chosen - before a material exists. Frame heights per
second at camera A's median speed of 12.04 units/s:

| stratum | range | p50 | p90 |
|---|---|---|---|
| **V30** near floor | 14.3 | **1.321** | 2.651 |
| V30 floor mid | 30.0 | 0.631 | 1.267 |
| V30 near flank wall | 56.0 | 0.338 | 0.679 |
| V30 deep rear wall | 70.0 | 0.271 | 0.543 |
| V29 inner pylon ring | 64.0 | 0.296 | 0.594 |
| V29 main wall | 122.0 | 0.155 | 0.312 |

**V30 spreads image speed 4.88×; V29 spread it 1.91×.** And V30's fastest
stratum moves 4.5× faster than V29's fastest, because V29 had nothing nearer
than 64 units and V30's floor comes to 14.3.

---

## 4. Sizing methodology

Nothing was typed. `tools/race2_v30_stage.py` writes all three profiles from
the constants the envelope measured, and its `report` mode re-derives them:

```
course plan reach        measured    27.06  assumed    27.06  ok
camera eye reach         measured    45.68  assumed    45.68  ok
live bearing arc         75 - 240 deg
peak sectors             135, 150, 195, 210
wall radius                 64.00  (2.37x the course)
floor top (profile)          0.00
keepout points                 66
```

The profile is authored with its floor top at y = 0, and `race2_scene`'s
existing seam lifts the whole stage so that surface lands
`STAGE_FLOOR_CLEARANCE` (2.0) under the lowest point of the racing line. Every
height in a V30 profile therefore reads directly as "above the floor", which is
how a section drawing reads. On this course the lift comes out at **−2.60**.

---

## 5. The central floor

### 5.1 One new builder: `environment_stage._plates`

A deck ring is an annulus **by construction** - `_deck` refuses one whose inner
radius is not inside its outer - and that is correct for Race #1, where the
plate surrounds a heightfield and the ravine under the branches cut must stay
open. Race #2 stands on nothing.

`_plates` is the third deck kind: a field of rectangular panels with an
optional `under` base, `terrace` stepping and `radius` clip. It is ~110 lines
in the file that already builds decks, not a second framework. Rings are
untouched and every profile written before V30 builds exactly what it built.

### 5.2 The module is sized from the frame, and the frame is narrow

This took four attempts and each got it wrong in the same direction.

At 1080×1920 and camera A's 32–38° *vertical* field, the **horizontal** field
is about 21°, so the picture is `2·d·tan(10.6°)` wide at range `d`:

| framing | floor range | frame width at the floor |
|---|---|---|
| final sprint, near edge | 15.1 | **5.8** |
| final sprint, far edge | 36.2 | 13.9 |
| mid chase | ~40 | ~15 |
| hook | 50–80 | 19–30 |

| attempt | module | what it measured |
|---|---|---|
| 1 | 13.0 squares | at most one seam in the shot, usually none |
| 2 | 22.0 × 7.0 | panels **wider than the frame**; read as a staircase |
| 3 | 52.0 × 4.0 strips | 1.5 seams across the sprint's near ground |
| **4** | **52.0 × 2.2 strips** | 4–5 seams in the narrowest framing |

**Two scales, not one.** The fine module is 2.2 units; every fourth strip is
`hall_deck_mid`, which puts a coarse accent every 9.8. The sprint sees the fine
rhythm, the hook sees the coarse one and reads the fine one as a surface rather
than as a pattern - which is Part K's "noisy grid" warning answered by having
two scales instead of choosing one.

**Strips, not a grid.** Two-unit squares over a 160-unit floor is five thousand
plates. The seams that do the work run *across* the direction of travel, so the
longitudinal ones can be three instead of eighty. At 12.04 units/s over a
2.45-unit pitch that is **4.9 seams a second** — Part G's speed cue, bought from
the floor for about two hundred meshes.

### 5.3 Two corrections the floor forced

**The station kerbs were blanketing the shot.** The first build put a
34 × 30 pad under the run-out. The final sprint's visible ground is a patch
roughly 22 × 11, so that pad measured at **100% of the frame** and hid the
entire panel rhythm behind it; the shot rendered as one smooth gradient with no
edge anywhere. The kerbs are now sized to their stations (12–16 units), and
**there is deliberately none at the run-out at all**.

**The joint was a canyon, not a line.** 2.6-unit plates standing 1.6 above a
near-black base put every seam in full shadow, and the floor read as
high-contrast corduroy - the loudest thing in a frame whose job is to be quiet.
The panels are now 0.6 thick on a base 0.75 below them, and the base is
authored close to the panel value rather than near black.

---

## 6. Concept A — central machine bay  ·  `contained_bay_v30`  ·  **the winner**

A continuous machine floor with a layered perimeter above it.

- **Floor** 2.2-unit strips across the direction of travel, 3 columns × 66
  rows, continuous to r ≈ 80, on a base showing through the joints. No hole,
  no terrace.
- **Wall** the live arc only, as three articulated bands at three depths —
  **56** on the near flank (90–150°), **70** across the deep rear (150–210°),
  **60** on the far flank (210–255°) — under one plainer upper band at 70 with
  a ±2-unit radius cycle.
- **Pylons** eight columns at r = 48 between the floor and the wall: the third
  parallax speed.
- **Bays** two, on `drum` and `sweep`, offset into the live arc.
- **Practicals** eleven warm floor inlays plus warm slots at 0.13 of the lower
  band height — 1.7 units above the floor, because the base of the wall is the
  only part of it the middle and the sprint contain.

The three-depth wall is **the one idea concept B contributed to the winner**,
and it was taken because it measured: swapping A's original uniform 64-unit
band for B's split moved the film's near-black from 0.79% to **0.21%** and its
warm coverage from 0.434% to **0.565%**, for 18 meshes.

## 7. Concept B — horseshoe arena  ·  `horseshoe_arena_v30`

Three walls at three depths around a continuous floor, open on the half of the
compass camera A never looks at, plus a raised plinth under the course itself.

Its asymmetry is the strongest answer to Part F in the set, and it is why the
winner carries its wall. It loses on two counts: the plinth dominates its
surface budget (`hall_deck_mid` at 40.97% of the film), and its hook holds
13.80% near-black where A holds 1.25%.

## 8. Concept C — stepped studio chamber  ·  `stepped_chamber_v30`

Depth from treads rather than height: the terrace starts at r = 34 and steps
down 1.5 every 13 units, under three low wall bands at 52, 62 and 74.

It is the most sculptural and the most expensive — 647 meshes and 166,592
triangles, 76% more than A — and it fails the hook outright at **30.53%**
near-black, because the terraced floor falls away exactly where the opening
frame looks. Rejected.

---

## 9. Material direction

No new environment framework and **one** new palette key. V27's eleven contained
keys are re-tuned through per-profile overrides, so `contained_hall_v272` is
byte-identical to what V27.2 shipped.

`hall_deck_mid` is the twelfth key and V30 is why there had to be one: V27's
floor is two values, which is enough for a floor that is a *surround*. V30's
floor is 43.5% of the film and up to 77.8% of a single frame, and at that size
a two-value floor is one value and a hole.

### 9.1 The blue cast, and what it actually was

The brief says the old hall was too navy. It is, and the cause was not the
paint.

Measured room chroma (max channel − min, over max) on one final-sprint frame:

| change | chroma | note |
|---|---|---|
| V27 floor value `#2D323A` | 0.338 | blue/red ratio 1.41 |
| white 6, exposure 0.60 | ~0.35 | **darker: worse** |
| white 4, exposure 0.46 | ~0.39 | **darker still: worse again** |
| filmic tonemap | 0.25 | racers fall 211 → 176 |
| reinhard tonemap | 0.22 | racers fall to 154: unusable |
| saturation 1.0 | 0.25 | racers lose their candy |
| **floor `#443A2C`** | **0.156** | **blue/red 1.01** |

A cyan rim light, a blue sky and a cool ambient were each suspected, tested in
isolation and **cleared**: with all four directional lights at zero energy and
ambient at zero, the floor still rendered at a blue/red ratio above 11.

The mechanism is the tonemapper. `grade.white` is 12.0, so a dark surface is
scaled far down before the ACES curve, and ACES is not a per-channel curve — it
carries matrices that shift hue, and in the toe they shift it toward cyan. The
signature is that **the cast got worse every time the room was darkened**,
which no additive explanation survives.

So the tonemapper stays — it is what keeps the racers at 211 — and the floor is
authored warm enough to come out neutral through it. **That number is a
pre-compensation, not a colour**: if a later edition moves `grade.white`, the
tonemap or the saturation, it must be swept again.

### 9.2 The cost of that choice

A floor light enough to render neutral is a floor at mean luma ~46, against the
outdoor control's 14.4. **In this pipeline you can have a neutral floor or a
dark floor, not both**, and V30 chose neutral. The racers stay 87.9 luma above
the room and the machine 153.0 above it, so the hierarchy holds — but a later
pass that wants a darker room will have to move the tonemapper, not the paint.

---

## 10. Lighting

All four world lights off the blue. That is not taste: the floor is seen
between 20° and 58° below horizontal, and at the grazing end a dielectric's
Fresnel term drives its specular toward 1.0, so the floor returns the *lights'
own colour* far more strongly than a wall does. Two cyan lights raking it at
−6° and −18° is a cyan floor.

The sky is chosen **as a light rather than as a picture** — it is never in a
frame, and its only remaining jobs are ambient and, through
`reflected_light_source`, every specular reflection in the room.

`floor_lift` is dropped from all three floor keys. It is a lifted black point
for rock the key never reaches; on the best-lit surface in the room it is a
constant added to most of the picture, and a constant is the one thing a
tonemapper cannot shape.

---

## 11. Warm practical visibility

**V29: 0.000%. V30 A: 0.565% of the film, present in 10 of 10 sampled frames.**

The fix is *where*, not *how bright*. V29's practicals were in wall bays sited
on Race #1's node names; V30's are in the floor, because the final sprint is
99.6% floor and a practical that is not in the floor is not in the shot that
matters. Their positions come from the sprint's own measured floor footprint —
a patch centred near (−14, 26) whose highest-traffic cells sit only 3.5 to 8.7
units off the racing line, so those inlays carry a clearance of 6 rather than
13. A flush inlay 0.1 proud of the floor cannot obstruct anything, which is the
same argument `_deck` already makes for a pad under a mechanism.

They were also too bright at first. At emission energy 1.9 a strip clips to
paper white and stops being warm; it is 0.62 now, and 0.55 units wide.

---

## 12. Surface-coverage audit (Part D)

`python tools/race2_v30_surfaces.py` — marker render, flat unshaded albedo per
family, **linear tonemap at unit white and unit exposure**. The first version
of that tool omitted the grade and reported nine of twelve families "unseen" in
a room whose walls are plainly in the frames; `tools/race2_v29_surfaces.py`
had already documented the trick.

Concept A, over the ten sampled moments:

| family | coverage | frames | peak | at |
|---|---|---|---|---|
| `hall_deck` | 43.47% | 10/10 | 77.79% | winner |
| `hall_deck_mid` | 13.64% | 10/10 | 21.30% | final_frame |
| `hall_grate` | 12.15% | 9/10 | 45.01% | switchback |
| `hall_panel` | 11.19% | 7/10 | 42.55% | hook |
| `hall_panel_dark` | 5.20% | 5/10 | 18.68% | central_chase |
| `hall_trim` | 3.46% | 7/10 | 11.10% | hook |
| `hall_rib` | 2.66% | 7/10 | 9.05% | early_chase |
| `lit_hall_warm` | 0.61% | 10/10 | 2.17% | winner |
| `lit_hall_cool` | 0.17% | 2/10 | 1.26% | sprint_early |
| `hall_deck_dark` | 0.09% | 10/10 | 0.30% | final_frame |

**Authored families seen: 10 of 10. Authored but unseen: 0.** All three
concepts score the same. V29 had six at 0.000%.

Two families are authored by no V30 concept and that is itself a Part D result:

- **`hall_glass`** — all three carried dark-glass inserts until the marker
  render measured them at 0.0000%, 0.0000% and 0.0018%. An insert at 0.62 of
  the band height is above the picture everywhere, because the frame top never
  rises above −9.10°. Removed from all three.
- **`hall_beam`** — overhead structure, which the same −9.10° rules out
  entirely. Never authored.

---

## 13. The measurements

Ten moments across the film, five worlds, all through the same renderer on the
same frames. Coverage is taken against a per-world silhouette matte; the check
is that machine-plus-racer coverage must be identical geometry in every world,
and it is: **6.85% in all five**.

| | outdoor | **v29 hall** | **A** | B | C |
|---|---|---|---|---|---|
| near-black, film | 4.23% | **67.04%** | **0.21%** | 1.49% | 7.29% |
| near-black, final sprint | 3.81% | **94.02%** | **0.04%** | 0.07% | 0.07% |
| lower-third near-black | 5.72% | 96.04% | **0.23%** | 0.21% | 0.24% |
| room mean luma | 14.4 | 5.0 | 46.3 | 44.4 | 42.4 |
| racer − room luma | 116.3 | 66.4 | **87.9** | 89.7 | 91.7 |
| machine − room luma | 187.4 | 112.3 | **153.0** | 154.9 | 156.9 |
| warm practical coverage | 0.000% | **0.000%** | **0.565%** | 0.202% | 0.278% |
| room blue/red (lit px) | — | **1.95** | **1.18** | 1.23 | 1.31 |
| environment coverage | 93.15% | 93.15% | 93.15% | 93.15% | 93.15% |
| meshes | 168 | 493 | **367** | 416 | 647 |
| triangles | 71,520 | 128,672 | **102,752** | 113,924 | 166,592 |
| ms/frame @1080×1920 | 211 | 141 | **196** | 191 | 180 |

Per moment, near-black:

| moment | outdoor | v29 hall | A | B | C |
|---|---|---|---|---|---|
| hook | 1.68% | 30.23% | **1.25%** | 13.80% | 30.53% |
| early_chase | 5.63% | 39.31% | 2.85% | 0.03% | 13.42% |
| first_mechanism | 3.63% | 29.38% | 1.94% | 0.02% | 26.51% |
| central_chase | 5.72% | 54.60% | 0.70% | 0.69% | 2.03% |
| switchback | 5.56% | 87.74% | 0.10% | 0.00% | 0.10% |
| late_mechanism | 4.80% | 53.09% | 0.02% | 0.03% | 0.00% |
| sprint_early | 1.55% | 87.04% | 0.02% | 0.06% | 0.09% |
| sprint_mid | 4.42% | 95.01% | 0.01% | 0.04% | 0.02% |
| winner | 5.27% | 97.86% | 0.04% | 0.11% | 0.06% |
| final_frame | 3.98% | 96.18% | 0.08% | 0.09% | 0.10% |

### 13.1 The winner, over all 1150 frames rather than ten of them

The table above samples ten moments. The delivered film was then measured
frame by frame, which is the number the brief's Part Q actually asks for:

| | value |
|---|---|
| frames | **1150** |
| near-black, mean over the film | **0.384%** |
| near-black, 99th percentile frame | 5.39% |
| **near-black, worst single frame** | **8.85%** |
| frames above 10% | **0** |
| frames above 25% | **0** |
| lower-third near-black, mean | 0.220% |

| shot | frames | mean | worst frame |
|---|---|---|---|
| `release` | 134 | 1.467% | 8.85% |
| `upper` | 407 | 0.488% | 1.79% |
| `middle` | 220 | 0.043% | 0.19% |
| **`run_in`** | **388** | **0.080%** | **0.44%** |

**Not one frame of the film reaches the brief's 10% target, let alone its 25%
failure line**, and the final sprint - 388 consecutive frames, the shot V29
lost at 90.8% - averages 0.080% and never exceeds 0.44%.

---

## 14. Shot by shot

**Hook (0.00–2.23).** A holds 1.25% near-black. The start bay reads against the
near flank wall at 56, `hall_panel` peaks here at 42.55% and `hall_trim` at
11.10%, and a warm inlay is in frame. No slab behind where a title would sit;
nothing bright under it.

**Early chase (2.23–5.20).** The floor's transverse seams sweep the frame at
~4.9 a second and the pylon band at r = 48 supplies the third speed. `hall_rib`
peaks here.

**Mechanisms.** No mechanism-specific set anywhere. The two bays are general
architectural modules offset into the live arc — a landmark at a race node is
where the camera is not looking, which is what sited them off the node.

**Switchbacks (9.60–13.60).** The three wall depths are what carries
orientation: 56 near, 70 deep, 60 far. A viewer cannot tell one 15° sector of a
constant-radius wall from another, which is precisely why the single-band
version measured worse.

**Final sprint (12.68–19.15).** 0.04% near-black against V29's 94.02%. Section
3.3 is the honest account of what it is: floor, the machine's own structure,
and warm inlays placed inside the sprint's own footprint. It is no longer a
black hole; it is not a set.

---

## 15. Phone review, 270×480

From `docs/validation/race2/v30_stage/sheet_150.png`.

| question | answer |
|---|---|
| can I track my colour? | yes in all ten moments, A and B; C loses the hook |
| does the room read as architecture? | A and B yes; the three wall depths are legible |
| is the track obvious? | yes — the pearl running surface is the brightest thing after the racers |
| is the floor support or noise? | support, after the two-scale rhythm; it was noise at attempt 2 |
| are warm accents visible? | yes, in every sampled frame for A |
| does it feel expensive? | closer than V29. See §17. |
| any giant black patches? | none above 2.85% in A |

---

## 16. Concept selection

A wins on every void figure, on warm-practical coverage, on hue neutrality and
on cost, and it wins the hook by a wide margin. B wins spatial orientation, and
its wall is now A's. C is rejected: the most expensive and the only one that
fails a shot outright.

| criterion | winner |
|---|---|
| racer focus | C (91.7) then B then A (87.9) — all comfortable |
| machine focus | C then B then A — all comfortable |
| **final sprint** | A (0.04%) |
| camera-compatible depth | A |
| parallax | A (4.88× spread) |
| spatial orientation | B, grafted into A |
| **absence of black void** | **A (0.21%)** |
| premium quality | A/B |
| reuse potential | A (fewest course-specific numbers) |
| cleanliness | A |
| phone readability | A |
| **performance** | **A (367 meshes)** |

---

## 17. The art-direction questions, answered

1. **Does it look like a real designed room?** Mostly. The floor and the three
   wall depths read as designed; the late shots read as a floor more than as a
   room, and §3.3 explains why that is geometric.
2. **Does it feel premium?** Closer than V29 and not yet fully. The palette and
   the two-scale floor are premium; the room is thin on *objects*, because the
   camera gave nowhere to put them.
3. **Does it still look like a dark trench?** No — 0.21% near-black against
   67.04%.
4. **Claustrophobic?** No. The nearest wall is 57.7 from the lens.
5. **Is the race embedded?** Partly. Four station kerbs tie the machine to the
   floor; the run-out deliberately has none (§5.3), so the final sprint's
   machine does not terminate into anything.
6. **Does architecture provide speed?** Yes: 4.88× image-speed spread, 4.9 floor
   seams a second.
7. **Can I understand where I am in the switchbacks?** Better than a drum. The
   three depths are the mechanism.
8. **Repetitive during long takes?** The final sprint is the risk, and it is
   the honest residual weakness.
9. **Giant flat slabs?** None. Largest single authored surface is a 52-unit
   floor strip, 2.2 deep.
10. **Too blue/navy?** No — 1.18 against the hall's 1.95, threshold 1.35.
11. **Are warm accents visible?** Yes, 10 of 10 frames.
12. **Does the environment stay secondary?** Yes, but by less than outdoor:
    racers 87.9 above the room where outdoor is 116.3.
13. **Could country racers work here?** Yes. The room carries no hue of its
    own; chroma 0.156.
14. **Could a different race use this stage?** Yes, with a re-run of the
    envelope tool. Nothing is seeded on hero seed 8.

---

## 18. Remaining weaknesses

1. **The room is brighter than the outdoor control** (46.3 vs 14.4). §9.2: in
   this pipeline, neutral and dark are mutually exclusive. A later pass should
   attack the tonemapper, not the paint.
2. **Cool specular on the floor.** `cool_coverage` is 6.25% for A — bright,
   slightly blue floor highlights from the near-white key. The mean hue is
   neutral; the highlights are not.
3. **The final sprint is a floor, not a set**, and no environment can change
   that without moving the camera. §3.3.
4. **No kerb at the run-out.** Correct for the frame, wrong for Part L's
   "supports terminate into deck" at the one station the film ends on.
5. **`lit_hall_cool` is in only 2 of 10 frames.** Authored and seen, so it
   passes Part D, but thinly.
6. **B and C are compared at ten sampled moments, not frame by frame.** Only
   the winner has the full-film measurement in §13.1.

---

## 19. Production recommendation

**`contained_bay_v30` is ready for production integration on Race #2 with
camera A**, subject to one caveat: it has been validated against *this* camera
and *this* course. Re-run `tools/race2_v30_envelope.py` before pointing it at
anything else — that is the tool whose absence produced V29.

Preserved from V29 and not to be reverted: the Race #2 environment seam, the
`EnvBuilder.apply_palette` call, `--environment` support, the stage-profile
plumbing, the rigid-lift placement rule and the flat-ground terrain config.

Added by V30: `environment_stage._plates`, the plate-aware `_stage_datum`, and
the profile's own lens keep-out passed through the seam.

---

## 20. Where everything is

| | |
|---|---|
| profiles | `godot/assets/marble_machine/environment/profiles/{contained_bay,horseshoe_arena,stepped_chamber}_v30.json` |
| new deck builder | `godot/assets/marble_machine/environment/environment_stage.gd` — `_plates` |
| new palette key | `godot/assets/marble_machine/lab_palette.gd` — `hall_deck_mid` |
| the seam | `godot/scripts/race2_scene.gd` — `_build_stage`, `_stage_datum` |
| envelope tool | `tools/race2_v30_envelope.py` |
| profile writer | `tools/race2_v30_stage.py` |
| review + clips | `tools/race2_v30_review.py` |
| surface audit | `tools/race2_v30_surfaces.py` |
| evidence | `docs/validation/race2/v30_stage/` |
| films | `exports/race2_v30_stage/` |
| tests | `tests/test_race2_v30_stage.py` |

`output/` and `exports/` are not in git, per this repository's convention.

### 20.1 Tests

`tests/test_race2_v30_stage.py` is 31 tests in four groups: the locks (the hero
race, camera A's four shots and 6.47 s sprint with no frame missing, that no
physics/camera/course module moved, and that V26 and V27.2's files are
byte-identical to the base), the architecture (floor continuity, no hole, walls
only on the live arc, no wall inside the camera's reach, no canopy, Race #2's
own lens guide, the seam), the measurements (near-black over all 1150 frames,
warm coverage, hue, parallax, cost, and zero authored-but-unseen surfaces), and
that **V29's hall still fails in exactly the way it failed**.

The selection covering this branch - race2, environment, v23, v26, v27, v29,
v30 - is **620 passed, 17 skipped, 0 failed**. Five tests in
`test_sloped_v251_world.py` and `test_sloped_v252_world.py` fail in a fresh
worktree because they read `output/sloped_race_v1/cameras_v221_5432.json`, a
Race #1 artefact that is not in git; they are outside this selection and
unrelated to this branch.
