# V32.1: the raceway was never behind the rail

**Branch** `v321-track-geometry-readability-final`, from
`origin/v32-race2-production-final` at `ab5d516`.
**Scope** the Race #2 channel's **render** geometry and how much of the strip is
drawn. No physics, no replay, no seed, no course, no collider, no camera, no
environment, no light, no grade, no racer, no overlay, no audio.
`tests/test_race2_v321_geometry.py::test_the_branch_changes_only_render_and_measurement`
asserts the whole diff against the base by filename, so the scope is a test
rather than a claim.

---

## 1. The problem, as the brief states it

> the low RB chase camera mainly sees the camera-facing guard / edge of the
> track while much of the actual broad lane surface sits behind it … the viewer
> often perceives marbles + bright rail + environment instead of marbles
> travelling on a clearly visible physical raceway.

The description of the picture is exactly right. Every word about the cause is
wrong, and so was V31.1's, and so was this pass's first two hours of work.

---

## 2. Part A — what is actually in front of the deck

### 2.1 Reproducing V31.1's instrument

`--track=bands` paints the channel as four flat unshaded classes - cradle, lip,
wall face, crown - with fog, tonemapping, grade and MSAA off, so a pixel's class
is a fact about the frame rather than a guess about it. Re-run on this branch at
V31.1's own thirteen moments it returns V31.1's own table to the third decimal
(grid `0.375 / 0.033 / 0.282 / 0.030`, drum `0.000 / 0.445 / 3.437 / 0.348`).
The instrument is the same instrument.

Its headline is unchanged: **the cradle covers 0.000% of the frame on eight of
thirteen racing moments and never more than 0.066% of any of them.**

### 2.2 The cross-section, measured

`race2.track.capped_profile(2.0)` is 21 points, in layout units:

| band | across | up |
|---|---|---|
| cradle | 0.000 … ±1.880 | −0.520 … −0.098 (a dish 0.422 deep) |
| lip | ±1.900 … ±2.000 | −0.020 … +0.530 |
| guard | ±2.004 | +0.560 … +0.580 (capped from 1.08 by `WALL_CAP`) |

**The rail stands 0.678 above the cradle's own edge in 0.124 of lateral run** -
a face at 79.6 degrees, five eighths of the section's height in three per cent
of its width. It is a fence at the edge of a dish, and it is the obvious
suspect. The brief's Parts B and C are written around it.

### 2.3 The suspect has an alibi

The first instrument built here cast one ray per section point from the
production camera at the station the racers were actually on, against the
course's own triangles, and reported the deck **visible at every one of the
twenty-one moments**, 400-odd delivery pixels wide. The renderer says
0.000%. One of them was lying.

The ray test was. It treated the channel as a solid tube. It is not:
**the channel is an open strip of single-sided triangles**, so half of every
ring is neither drawn nor able to occlude, and which half depends on where the
camera is. A ray test against a surface the renderer never draws is measuring a
tube that does not exist.

The replacement is a z-buffered label pass over the same triangles in the same
winding `race2_scene._strip_mesh` emits, with the same screen-space cull.
Validated band by band against the GPU: cradle and lip agree to under 0.05 of a
per cent, and the wall/crown **sum** agrees to 0.6 (a crown four pixels wide on
the delivery frame is one pixel at the rasteriser's 540, and a point sample
cannot be narrower than its own pixel).

That instrument answers the question the pixel count cannot: **of the pixels
where a deck surface exists but is not the nearest thing, what is in front of
it?**

The answer, on every one of the twenty-one moments, is **nothing**. Between 46%
and 97% of the missing deck has no surface at all between it and the camera.

### 2.4 The cause

`race2_scene._strip_mesh` winds the strip so that the side Godot draws is the
**outside of the shell**: the underside of the cradle and the *outer* face of
each guard. The running surface is backfacing to every camera above the track,
and the rasteriser discards it before depth is ever considered.

**The white ribbon in the delivered film is the outside of the near rail.** The
road is not behind it. The road is not being drawn.

Proved in the renderer rather than argued, with one field changed and everything
else - geometry, material, camera, lights, environment - held:

| t | deck, front faces only (V32) | deck, both faces |
|---|---|---|
| 3.20 | **0.000%** | 2.070% |
| 8.40 | **0.001%** | 44.542% |
| 15.40 | **0.000%** | 10.851% |

### 2.5 The third face mode, built and rejected

`CULL_DISABLED` is not the only way to draw the running surface. `CULL_FRONT` -
`--faces=inside` - draws the channel's inner surface and discards the shell's
outside, which reveals the same deck and, because the underside of the strip is
never drawn, would have left the upper frame the dark room it was and saved the
payoff card (section 11).

It was rendered and rejected on the picture. With the near guard's outer face
gone the ribbon has no near edge: the road runs to the far rail and then simply
stops, and the track reads as a cut-away rather than as an object. `both` gives
it a bottom and a thickness, which is what makes it read as a moulding a marble
could be inside. The card was moved instead.

### 2.6 Why V31.1's material pass could not have fixed it

V31.1 measured the visible band's value, its spread, its warmth and its response
to every gloss field, and concluded - correctly - that albedo distribution
across the section was the only live lever. Every one of those measurements was
taken on the guard face, because the guard face was the only thing on screen.
Its Variant B profile lifts the cradle by a gain of 1.35 and that gain has never
once reached a pixel. **No material can shade a polygon that is discarded before
shading.**

---

## 3. Part B — the render/collision separation

`race2.export._run_rings` and `sloped.track.TrackRun.local_colliders` build the
same rings from the same `section_at`. `race2.export`'s own docstring is the
argument for that arrangement - "a second hand-built copy would be a second
chance to be wrong" - and it is why V31.1 was forbidden the geometry outright.

V32.1 keeps the arrangement and adds one seam to it, at one call site:

```
race2/export.py   _run_rings()   section = v321_section.transform(variant, run.section_at(i))
sloped/track.py   local_colliders()   ring_points(..., run.section_at(i), ...)   <- untouched
```

`local_colliders` does not import `race2.export`, so it cannot see the
transform even by accident. `test_the_render_variant_never_reaches_the_collider`
walks every run's collider mesh with each variant set and compares the vertex
list byte for byte; `test_the_weld_never_reaches_the_collider` does the same for
the other render-only change.

Two switches, both off by default, both environment variables for the reason
`race2.track.WALL_CAP` gives for its own - four tools write geometry files
through one function, and a threaded parameter would be a parameter four call
sites could disagree about:

* `RACE2_RENDER_SECTION` - the cross-section map (Part C)
* `RACE2_RENDER_WELD` - the run-join weld (section 6)

and one render flag, `--faces=front|both`, defaulting to `front`, which is V32's
render exactly. **`build` asserts that CONTROL reproduces the shipped
`race2_switchyard_8.geometry.json` byte for byte before anything is rendered.**

### What a cross-section variant may do

A pure map from a section to another of the same length - the strip joins rings
column by column and `race2_track_surface` paints its bands from
`u = column / 20`, so a changed point count would repaint the track as well as
reshape it. It may move `up` down and `across` out. Never the reverse: inward
and upward is where the marbles are.

---

## 4. How much of the fence is load-bearing

Lowering a rail the marbles lean on would put a racer in mid-air. So the rail
was measured rather than assumed, over every frame of the delivered film.

| | |
|---|---|
| marble-frames inside a channel run | 7765 |
| resting on the lip or the guard face at all | 109 (**1.40%**) |
| median contact height, as a fraction of the face | 0.237 |
| 90th percentile | 0.339 |
| 99th percentile | **0.396** |
| highest contact | **0.856** |

**The maximum is a single frame.** m3, in `corr1`, at t = 2.433 - one sample of
7765, and the second-highest contact in the whole film is below 0.45. What a
lowered render face costs is therefore not a risk, it is a table:

| render face kept at | marble-frames above it | worst overshoot |
|---|---|---|
| 0.85 | 1 | 0.004 layout (0.02 marble radii) |
| 0.80 | 1 | 0.038 (0.13 radii) |
| **0.70** | **1** | **0.106 (0.37 radii)** |
| 0.60 | 1 | 0.174 (0.61 radii) |

A and B keep the face at 0.70, C at 0.90. All three clear the 99th percentile
with room; the one frame where m3 leans higher than A's or B's render face is
1/1150 of the film and overshoots by about a third of a marble radius.

---

## 5. Part C — the three cross-sections, and the fourth candidate

Each candidate is the winding fix plus one cross-section. **S is the winding fix
with no cross-section change at all**, and it is in the set because the honest
control for "does lowering the guard help?" is "the same picture with the guard
where it is".

| variant | faces | face height | drop | face run | face angle | section half | shelf |
|---|---|---|---|---|---|---|---|
| CONTROL | front | 0.6781 | — | 0.1240 | 79.6° | 2.0040 | — |
| **S** | both | 0.6781 | 0.0000 | 0.1240 | 79.6° | 2.0040 | — |
| **A** | both | 0.4747 | 0.2034 | 0.1240 | 75.4° | 2.0040 | — |
| **B** | both | 0.4747 | 0.2034 | 0.5716 | 39.7° | 2.4516 | 0.4476 |
| **C** | both | 0.6103 | 0.0678 | 0.6740 | 42.2° | 2.5540 | 0.5500 |

**S — the winding fix alone.** No vertex moves. The picture traces the collider
exactly, which no other candidate can say.

**A — lower visual guard.** Every point above the cradle edge keeps its lateral
position and 0.70 of its rise. The conservative reveal, and the one with no
second effect to argue about.

**B — tapered guard, deck exposed.** A's height, with each point's top leaned
outward by 2.20 of the height it lost. The face becomes a 39.7° bank the camera
looks *over* rather than a 79.6° fence it looks *at*, and the ribbon gains
0.45 of pale shoulder outside the collider.

**C — render-only shoulder.** The brief's Part C asks for "a thin broad
render-only pearl lane surface above the hidden track deck". Once the deck is
known to be backfacing rather than hidden, a surface *above* it would cover the
real road, so C is built as the nearest thing that is not a mistake: the face
keeps 0.90 of its height and slides 0.55 outward, and the span it vacates
becomes a flat shelf at the cradle's own edge height. It is outside the collision
wall, so nothing can ever touch it - the only candidate that changes nothing at
all about where a marble may be seen resting.

---

## 6. The seam the fix uncovered

Consecutive runs never met. Measured on the delivered course, the last ring of
each run stands **0.051 to 0.077** layout units from the first ring of the next
at the centreline and **0.11 to 0.36** at the section edges, because the bank and
the width are still changing across the join. The collider has the same gap and
always did; a marble crosses it inside one frame and never notices.

With the deck backfacing, so did the picture - there was no surface for a hole to
be a hole in. With the deck drawn, each join is a **black slash across the
road**: 6.5 to 48.8 delivery pixels wide, on screen at **16 of the 21** sampled
moments.

`RACE2_RENDER_WELD=1` replaces each run's last ring with the next run's first
ring, so the two strips share an edge instead of facing each other across a gap.
Longitudinal rather than lateral, so it is not a cross-section change; render-
only, by the same call-site separation as the sections. The bridging quad it
creates is 0.77 to 1.25 times the run's own sample step, so nothing stretches and
nothing folds.

| variant | weld | worst world gap | worst on screen | joins in frame |
|---|---|---|---|---|
| CONTROL | no | 0.3565 | 48.8 px | 16 / 21 |
| S, A, B, C | yes | **0.000000** | **0.0 px** | 0 / 21 |

It is applied to every candidate and not offered as a choice, because a hole in
a road is not a matter of taste.

---

## 7. Part E — visible deck, measured two ways

Two instruments, because one of them can be argued with. **`expose`** is the
analytic rasteriser at 540x960: it knows which surface each pixel is by
construction. **`bands`** is the GPU painting the same four classes and a
classifier counting them. They are built on different code and agree on the
ordering and the magnitude of every row below.

`lane px` is the widest **contiguous** run of deck on the racers' own screen
row, scaled to the 1080-wide delivery frame. It is the number the brief's Part E
asks for and it is deliberately not the deck's area: a sliver of deck running
away up the frame is one pixel on every row it crosses, however many pixels it
adds up to.

### Godot's own count, 21 moments

| | deck % of frame | lane px | lane / track | deck / channel | moments with lane >= 40 px |
|---|---|---|---|---|---|
| **CONTROL** | **0.034** | **0.1** | **0.000** | 0.028 | **0 / 21** |
| S | 15.32 | 252.6 | 0.511 | 0.568 | 15 / 21 |
| **A** | **16.18** | **294.2** | **0.580** | **0.669** | **15 / 21** |
| B | 17.35 | 341.8 | 0.682 | 0.662 | 17 / 21 |
| C | 17.14 | 315.0 | 0.573 | 0.559 | 16 / 21 |

### The analytic rasteriser, same 21 moments

| | deck % | lane px | lane / track | deck / channel |
|---|---|---|---|---|
| CONTROL | 0.036 | 0.3 | 0.000 | 0.029 |
| S | 16.996 | 424.1 | 0.639 | 0.612 |
| **A** | **17.954** | **474.0** | **0.761** | **0.708** |
| B | 19.207 | 507.0 | 0.803 | 0.695 |
| C | 18.976 | 495.6 | 0.729 | 0.598 |

The two disagree on the absolute lane width because the GPU's `bands` render
paints the racers black, so a marble cuts the run it is standing on, and because
a 540-wide point sample cannot resolve a four-pixel feature. They agree on
everything the choice depends on.

### Per moment, CONTROL against the winner

| moment | t | deck % ctl | deck % A | lane px ctl | lane px A | lane/track A |
|---|---|---|---|---|---|---|
| grid | 0.35 | 0.375 | 10.616 | 0 | 0 | — |
| hook | 1.20 | 0.214 | 27.464 | 0 | 224 | 1.000 |
| drop | 2.40 | 0.000 | 11.266 | 0 | 353 | 1.000 |
| drum | 3.20 | 0.000 | 2.874 | 0 | 71 | 0.362 |
| post_drum | 4.20 | 0.000 | 4.376 | 0 | 14 | 0.053 |
| sweep | 5.20 | 0.001 | 11.659 | 0 | 983 | 1.000 |
| chase | 6.80 | 0.066 | 8.138 | 0 | 580 | 1.000 |
| bend | 7.60 | 0.028 | 6.628 | 0 | 0 | — |
| **weak_in** | **8.00** | 0.010 | **10.691** | 0 | **592** | 0.548 |
| **switchback** | **8.40** | 0.001 | **45.137** | 0 | **491** | 0.952 |
| **weak_out** | **8.50** | 0.000 | **46.475** | 0 | **378** | 0.940 |
| gorge | 9.60 | 0.000 | 18.356 | 0 | 475 | 1.000 |
| sparse | 10.60 | 0.000 | 5.524 | 0 | 99 | 0.518 |
| mid_bend | 11.40 | 0.016 | 7.354 | 3 | 310 | 0.503 |
| late_mech | 12.20 | 0.000 | 47.503 | 0 | 484 | 1.000 |
| sprint_in | 13.60 | 0.000 | 5.722 | 0 | 100 | 0.295 |
| sprint_mid | 14.60 | 0.000 | 54.811 | 0 | 384 | 1.000 |
| comeback | 15.40 | 0.000 | 11.790 | 0 | 640 | 1.000 |
| line | 16.20 | 0.000 | 0.706 | 0 | 0 | — |
| after | 17.00 | 0.000 | 0.330 | 0 | 0 | — |
| runout | 18.00 | 0.000 | 2.362 | 0 | 0 | — |

The five moments with no lane are the five where no lane is the right answer:
`grid` is the start gate seen end-on, `bend` puts the racers on a rail-high row,
and `line`, `after` and `runout` are after the finish, where the camera has let
the racers roll out across the room and there is no track under them to show. On
every racing moment there is a lane, and on eleven of them it is the **whole**
width of the ribbon on that row.

---

## 8. Part I — the racer contrast guard

The risk this pass creates is precisely the one Part I names: a broad pale deck
could swallow the marbles. Measured per racer from the renderer's own per-racer
labels, never by clustering — V31.1 found that clustering on a sparse frame
splits one marble into four and returns a guard that cannot fail.

| | deck L* | deck clip % | **weakest racer dE vs its surface** | weakest vs room | moments under 12 dE |
|---|---|---|---|---|---|
| CONTROL | 32.4 \* | 0.000 | 26.04 | 17.87 | 0 / 21 |
| S | 92.67 | 0.151 | 19.63 | 18.01 | 0 / 21 |
| **A** | **92.76** | **0.106** | **19.47** | **17.91** | **0 / 21** |
| B | 93.16 | 0.082 | 19.40 | 18.05 | 0 / 21 |
| C | 93.16 | 0.051 | 19.43 | 18.08 | 0 / 21 |

\* CONTROL's "deck" is the handful of stray cradle pixels that exist at all. It
is not a surface anybody is looking at.

**The guard passes with room.** The weakest individual racer loses 6.6 dE
against the surface it stands on — from 26.0 to 19.5 — and 19.5 is still several
times a just-noticeable difference at these sizes. Separation from the room is
unchanged at 17.9. No racer on any moment falls under 12. The yellow, the cyan
and the pink winner are all in that set and none of them is the weakest.

Over the whole film, CONTROL clips 0.006% of its pixels and A clips 0.048%; the
99th-percentile luma goes from 211.5 to 242.1. **The deck now lives at the top
of the tone curve.** It does not clip — V21 shipped a film clipping 5.5% and that
was a defect — but it is the first thing any future exposure change would break.

### The material's cradle gain is not why the deck is bright

Part D locks V31.1's Variant B, whose profile lifts the cradle by a gain of
1.35. That gain had never reached a pixel. Now that it does, it is worth knowing
what it costs, so the same five frames were rendered with it and without it:

| channel material, `--faces=both` | deck L* | deck clip % |
|---|---|---|
| **B — V31.1 locked, cradle gain 1.35** | **90.93** | **0.183** |
| A — the same pearl, no gain across the section | 88.23 | 0.176 |
| v31 — `#D2D8DE`, the pre-V31.1 control | 90.21 | 0.147 |

**2.7 L\* separates the locked material from a completely ungained one**, and
V31's own control lands between them. The deck is bright because it is a large
near-horizontal surface newly turned toward the key, not because of anything
V31.1 chose. Part D's lock costs nothing, and it is kept.

---

## 9. Part J — mechanism readability

| | mechanism % of frame | mechanism L* | dE, mechanism vs deck |
|---|---|---|---|
| CONTROL | 2.792 | 60.70 | 62.16 |
| S | 2.791 | 61.77 | 62.39 |
| **A** | **2.930** | **61.23** | **62.95** |
| B | 3.019 | 61.05 | 63.49 |
| C | 2.995 | 61.16 | 63.28 |

The drum, the sweep, the pair and the last mechanism cover **more** of the frame
than before, not less — a lower guard reveals a little more of each station's
foot — and they separate from the deck slightly better, because a pale surface
behind a saturated gold-orange blade is a better background for it than a dark
room seen at a grazing angle. Nothing is swallowed.

---

## 10. Parts F and G — route continuity, the switchback, and the sprint

**6-14 s.** Nine of the eleven moments in that window carry a lane, and on five
of them the lane is the entire ribbon on that row. `weak_in` at 8.00 s goes from
0 to 592 px of contiguous road, `mid_bend` at 11.40 from 3 px to 310,
`late_mech` at 12.20 from 0.000% deck to 47.5%.

**The switchback.** 8.40 and 8.50 s are the two moments the course folds hardest
back on itself, and they are where the fix does the most: **the deck goes from
0.001% and 0.000% of the frame to 45.1% and 46.5%**, with a lane that is 95% and
94% of the ribbon's width on the racers' own row. On the 270x480 sheet the
hairpin reads as a hairpin — a broad U of road with the bend's direction plain —
where V32 has two marbles and a bright thread.

**The final sprint, 14 s to the line.** One take, no cuts, the RB camera
untouched. `sprint_mid` at 14.60 s carries 54.8% deck and a lane that is the
whole ribbon; `comeback` at 15.40 s carries 11.8% and 640 px. The pink winner's
pass on the green happens over a surface that is visibly a surface.

---

## 11. Part V — the payoff card, and the one thing the fix broke

The first attempt at the production candidate stopped on V32's own guard:

    the card's ink [112, 1695, 966, 1920] leaves its band [1731, 1920]

`race2.presentation.card_band` places the payoff card in the tallest run of rows
that stays under 130 luma across the text corridor for the whole of the card's
life and carries no still-racing marble. On V32 that band is **`[97, 372]`, 275
rows at the top of the frame**. Measured on the same frames with the running
surface drawn, the run-out sweeps through those rows and **no window of the
card's height anywhere in the frame stays under the bar** — the best available
is 184 against a limit of 130.

**V32's payoff card was sitting in a band that was only dark because the raceway
was not being drawn.** Part V anticipates exactly this — "no overlay redesign
unless geometry physically creates a collision" — and the collision is now a
measurement. The card's drawing, type, colour, content and timing are untouched.
Two things changed in the *placement rule*, and the first of them is a bug fix
that has nothing to do with this pass:

1. **The frame's own bottom gutter.** `HOOK_TOP` is already "the frame's gutter,
   applied vertically" for the hook. The card never needed it while its band was
   at the top of the picture. The first film whose darkest band was the floor
   put the fact line flush against the frame's last row — a margin failure a
   top-aligned band can never produce and therefore never caught.

2. **A fallback for a film with no band.** `brightest` is the worst pixel
   anywhere across an 888-pixel corridor on any frame of the card's life. That
   is the right test for *choosing* a band out of a dark picture and it is far
   stricter than the question it stands in for. When no band can hold the card,
   the rule becomes the question itself: slide a card-height window between the
   gutters, avoid any row a still-racing marble occupies, and take the one whose
   worst pixel **under the card's own glyphs** is lowest.

A third thing was wrong and is fixed on the way: `card_band` sized the band from
`v24_payoff`'s *default* winner. `v24_payoff` fits its type to the gutter, so
PINK's ink is 225 rows tall and PURPLE's is 201 — the band was being computed for
a card that was not going to be drawn. It now reads the winner off the replay it
is already holding.

The result, measured:

| frames | band | fallback | worst luma in band | **worst luma under the glyphs** | ink inside band |
|---|---|---|---|---|---|
| **V32 / CONTROL** | **[97, 372]** | no | **84.1** | — | yes |
| A (and S, B, C) | [1588, 1813] | yes | 184.0 | **67.6** | yes |

`test_the_card_band_is_v32s_on_v32s_frames` asserts that V32's frames still give
V32's band, its ink box and its `inside_band`, to the pixel. The card moves from
the top of the frame to the lower third **only on films that have a raceway in
them**, and it is more legible there than V32's is where it is: 67.6 against
84.1.

---

## 12. Parts T and U — the opening, and 8.0-8.5 s

**Part T: the opening fixes itself.** V32 noted the first half-second as
somewhat dark, and the brief said to review it after the geometry rather than
touch the grade. Measured, frame 0:

| | mean luma | 95th percentile |
|---|---|---|
| CONTROL | 38.05 | 97.6 |
| **A** | **72.69** | **243.2** |

The start pan is a large pale surface from the first frame, and the eight racers
sit on it. Nothing in the exposure, the grade or the environment moved. Over the
whole film the mean luma goes from 48.71 to 80.87.

**Part U: 8.0-8.5 s is no longer the weak interval.** Deck coverage goes from
0.010% and 0.000% to 10.7% and 46.5%, and both moments gain a lane — 592 px and
378 px, the second of them 94% of the ribbon. It is now one of the strongest
stretches in the film rather than the weakest. **Stop, as Part U says to.**

---

## 13. Part R — choosing, and why the widest lane did not win

Ranked on the brief's own list rather than on deck area:

| | lane px | lane/track | weakest dE | **guard face R−B** | face height | believability |
|---|---|---|---|---|---|---|
| CONTROL | 0.1 | 0.000 | 26.04 | +6.29 | 0.678 | the collider, exactly |
| S | 252.6 | 0.511 | 19.63 | +5.70 | 0.678 | the collider, exactly |
| **A** | **294.2** | **0.580** | **19.47** | **+5.15** | 0.475 | lateral silhouette unmoved |
| B | **341.8** | **0.682** | 19.40 | **−4.33** | 0.475 | +0.45 outside the collider |
| C | 315.0 | 0.573 | 19.43 | +2.60 | 0.610 | +0.55 shelf, outside the collider |

**B has the widest lane and B is disqualified by one number.** V31.1's central
finding about this room is that it adds about twelve bytes of red-minus-blue to
anything put in front of it, and that Variant B's albedo is cool *on purpose* so
that the rendered guard lands at about +4. B's flare turns the face forty degrees
away from the warm key and into the cool fill: the guard renders at
**R−B = −4.33**, a ten-point swing, and on screen it is a saturated blue kerb
running the length of the track. That is a fifth element in a hierarchy the brief
states as four — dark room, pearl deck, brighter silver rail, saturated racers —
and it is the least premium of the five candidates at phone size. It fails Part
D's *intent* without touching a single one of Part D's fields.

**C is the runner-up and loses on believability.** Its shelf is 0.55 of pale
surface that exists in no collider, and it still cools the rail to +2.60.

**A wins.** It is the only candidate that widens the lane materially — +17% over
S, and the ribbon goes from half road to 58% road — while leaving the ribbon's
lateral silhouette, the picture's trace over the collider and the rail's measured
warmth where V31.1 and V32 put them. It takes seven of the brief's ten criteria
at or near the top and loses only "maximum visible deck area", which the brief
says explicitly not to choose on.

**And S is the finding behind all of them.** S moves no vertex at all and
delivers 99% of the improvement. Every cross-section variant is worth between 4%
and 14% more deck on top of a change that is worth **four hundred times**
CONTROL's.

---

## 14. Parts M and N — the physics and camera proof

| | evidence |
|---|---|
| collider vertices | `test_the_render_variant_never_reaches_the_collider` walks all eleven runs' `local_colliders()` meshes with each variant set and compares the vertex list byte for byte. Identical. The weld has its own copy of the same test. |
| replay digest | `751031348936808792ad2fac667bfdfb6e726dca7520ffdaf19429c6a2f7f539` — V32's |
| event digest | `51078e8d31e56f53993c6ee9aa61b482a6757942a422fb43f533336983016502` — V32's |
| physics source | 7 files, all identical to `fa39d7a` |
| camera source | 6 files, all identical to `fa39d7a` |
| camera plan | every variant renders from a **byte-identical copy** of `race2_switchyard_8.cameras.json`. A camera cannot have moved between films rendered from the same bytes. |
| environment profile | `contained_bay_v301.json` identical |
| material | every colour, gloss, texture and gain field of V31.1's Variant B identical; `track_measure.json` regenerates identically over 6866 fields |
| regenerated reports | `events_switchyard_8.json` (697 fields), `read_RB.json` (167 fields), `track_measure.json` (6866 fields) — all identical |

V32's `stage_locks` reports two FAILs, and both are the pass itself:
`godot/scripts/race2_scene.gd` (reads `--faces`) and
`godot/assets/marble_machine/course/race2_track_surface.gd` (implements it). Its
lock list is by filename, so a file this pass exists to change is a file it must
flag. Every layer *inside* those files — the environment profile, the material's
fields, the regenerated measurement of the rendered track — is identical, and
`test_the_physics_and_camera_layers_did_not_move` asserts that those two paths
are the **only** two.

**The replay file** differs from the V32 branch's copy in exactly one field:
`summary.race.wall_seconds`, how long the simulation took to run. Both digests
match, and so does every other value in 12.6 MB of JSON.

### Three of V32's own tests now fail, and they should

Each pass in this repository ends with a test asserting that *that* pass touched
only its own files. Those assertions go stale the moment the next pass lands, and
they are left to go stale rather than edited, because editing them would be
rewriting an earlier pass's evidence. At `ab5d516` two of V31.1's were already
failing for exactly this reason - V32 added `race2/presentation.py`, which V31.1
had asserted it would never contain.

Measured on the base commit and on this branch:

| test | at `ab5d516` | here | why |
|---|---|---|---|
| `test_race2_v311_track::test_the_branch_changes_only_render_and_measurement` | **fails** | fails | V32 added `race2/presentation.py` |
| `test_race2_v311_track::test_no_locked_package_moved[race2/]` | **fails** | fails | the same file |
| `test_race2_v32_final::test_the_branch_adds_only_presentation` | passes | **fails** | V32.1 adds render geometry |
| `test_race2_v32_final::test_no_locked_file_moved[godot/scripts/race2_scene.gd]` | passes | **fails** | reads `--faces` |
| `test_race2_v32_final::test_no_locked_file_moved[.../race2_track_surface.gd]` | passes | **fails** | implements `--faces` |

Three new failures, and all three name one of the two files this pass exists to
change. Everything else in those two suites passes - 174 tests over the eight
Race #2 files, plus this branch's own 31.
`tests/test_race2_v321_geometry.py::test_the_branch_changes_only_render_and_measurement`
is V32.1's version of the same assertion and it is the one that is current.

---

## 15. Part S — the final production candidate

    exports/race2_v321_track_geometry/race2_switchyard_final_candidate.mp4
    exports/race2_v321_track_geometry/race2_switchyard_final_candidate_phone_270x480.mp4

Built by `tools/race2_v321_short.py`, which **contains no presentation and no
audio**: it imports `tools/race2_v32_short.py`, repoints four paths at variant
A's frames, and calls V32's own stages. The hook, the ring, the payoff card, the
soundtrack, the clock, the encode and the QC are not reimplemented, they are
called.

`qc` passes every check:

    1080x1920, 60/1 fps, 1150 contiguous frames, 19.1667 s
    0 temporal omissions, 0 duplicate frames, 0 black frames
    true peak -1.93 dBTP, integrated -14.18 LUFS, range 3.30 LU
    PICK A COLOR up on frame 0, gone at 1.30 s, clearing the racers by 200 px
    the ring opens on the crossing (15.8167 vs 15.8167), 0 of 42 frames blocked
    the card comes up 1.00 s after the result, ink inside its band [1588, 1813]
    the card says 5TH and both rank instruments agree
    every mark verified again on the delivered file

The loudness numbers are V32's to the hundredth of a dB, because the soundtrack
is synthesised from the same replay by the same code and re-encoded at the same
bitrate.

---

## 16. Parts H and Y — the phone review

Rendered at 270x480 and reviewed band by band
(`docs/validation/race2/v321_track_geometry/short/A/phone_review_*.png`).

| question | answer |
|---|---|
| 1. Is there visibly a real road? | Yes, from frame 0. The start pan is a pale surface with eight marbles on it before the first cut. |
| 2. Can I see its width? | Yes. On eleven of the sixteen racing moments the lane is the whole ribbon on the racers' row. |
| 3. Can I track my chosen marble? | Yes. Weakest racer 19.5 dE against the deck, 17.9 against the room, none under 12. |
| 4. Can I see where the course goes locally? | Yes — the bend's direction and the next section are both readable on every racing moment. |
| 5. Do switchbacks make sense? | Locally, yes. The full 180 is still not in one frame, which the brief says is not required. |
| 6. Does the track remain secondary to the racers? | Yes; it is a surface they are on rather than an object competing with them. |
| 7. Does the environment remain secondary? | Yes; it is untouched, and it is now the darker of two surfaces rather than the only one. |
| 8. Does the final sprint feel physical? | Yes. One take, RB camera, marbles visibly on a lane through the last hairpin and down the run-in. |
| 9. Is the winner obvious? | Yes — ring on m7 on the crossing frame, 0 of 42 frames blocked, PINK WINS in the lower third. |
| 10. Does it feel upload-ready? | Yes. |

On "premium, not neon": the guard renders at R−B +5.15, within a point of V32's
+6.29, and the deck clips 0.048% of the film. B's blue kerb is the one candidate
that would have failed this question, and it is the one that was rejected.

---

## 17. Remaining weaknesses

1. **The deck lives at the top of the tone curve.** 99th-percentile luma 242 of
   255, clipping 0.048%. Nothing clips now; any future exposure, grade or key
   change has to be checked against the deck first, which was not true of any
   previous pass because there was no deck.
2. **The channel's underside is now in frame.** `--faces=both` draws the outside
   of the strip as well as the inside, so in shots that pass under the course —
   the run-out, most visibly — a pale wedge of track bottom crosses the upper
   frame. It reads as the track having a thickness, which is an improvement on
   nothing being there, and it is what displaced the payoff card. A pass that
   wanted it gone would need per-shot control the camera lock forbids.
3. **One frame of one marble leans above its render rail.** m3, `corr1`,
   t = 2.433, by 0.106 layout units — about a third of a marble radius, for
   1/1150 of the film. Measured, bounded, and invisible in the frame (section 4).
4. **`bend` at 7.60 s and `post_drum` at 4.20 s carry the thinnest lanes** — 0
   and 14 px on the racers' own row — because at both the field is riding high on
   a bank and the row through it crosses rail rather than deck. Deck coverage at
   both is healthy (6.6% and 4.4%); it is the row measure, not the picture, that
   is thin.
5. **The cross-section variants are worth far less than the winding fix.** If a
   future pass wants more lane than A gives, the lever is not a lower guard — it
   is the room's fill on the guard's outer face, which is what turned B blue.

---

## 18. Should Race #2 development stop?

**Yes.**

The stop condition the brief sets is a list, and every item on it is met:

* a clearly visible physical lane — 0.034% of the frame to 16.18%, and a lane on
  every racing moment where a lane is the right answer;
* broad enough to read as a raceway — the ribbon is 58% road against V32's 3%;
* racers remain dominant — weakest 19.5 dE, none under 12, no racer lost;
* the route is locally traceable and the switchbacks are acceptable — the hardest
  fold in the course goes from 0.001% deck to 45.1%;
* the final sprint is strong — one take, 54.8% deck at 14.6 s, the comeback over
  a visible surface;
* physics unchanged — both digests, every collider vertex, seven source files;
* the RB camera unchanged — a byte-identical camera plan;
* the V30.1 environment unchanged — the profile file identical;
* V32's presentation and audio intact — the same code, called, at −1.93 dBTP and
  −14.18 LUFS, with the card's placement rule extended rather than redesigned.

The remaining weaknesses in section 17 are all of the kind the brief calls minor
imperfections. **Do not build V32.2, a V33 camera, a new environment or a new
track layout.**

---

## 19. Reproducing this

    export GODOT_BIN=~/Downloads/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe
    python tools/race2_camera.py --course=switchyard --seed=8 --out=output/race2 --quiet
    python tools/race2_v31_camera.py --seed=8 --only=RB --quiet
    python tools/race2_v321_geometry.py all           # contacts, sections, build,
                                                      # joins, expose, bands, contrast,
                                                      # mechanism, diagram, films, compare
    python tools/race2_v321_short.py all --variant=A  # the candidate; `locks` reports
                                                      # the two files this pass changes
    python tools/race2_v321_short.py qc --variant=A
    python -m pytest tests/test_race2_v321_geometry.py

`tools/race2_camera.py` and `tools/race2_v31_camera.py` rewrite two committed
reports with a new `wall_seconds` and, in the second case, a single-candidate
`compare.json`. Restore both afterwards — `git checkout <base> --
docs/validation/race2/events_switchyard_8.json
docs/validation/race2/v31_readability/compare.json` — or the branch will carry a
diff that has nothing to do with it.

---

