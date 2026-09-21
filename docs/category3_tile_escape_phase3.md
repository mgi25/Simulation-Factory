# Category 3, Test #1 — HIT EVERY TILE TO ESCAPE — Phase 3: Godot visual proof

**Decision: VISUAL PROOF PASSED.**

At the locked Phase 2 operating point — 17 sides, 3 tiles a side, 51 tiles,
gravity 0, 85 wu/s, one ball, no trajectory assistance — the natural runs are
readable as a 9:16 mobile Short. A viewer can follow the ball, tell an
activated tile from an inactive one at a glance, read progress without the
counter, find the single remaining target at 50/51, and feel the last-tile
wait. Nothing about the simulation had to change to get there.

One presentation requirement came out of it and is not optional: **at 30 fps
the ball needs a temporal trail.** Without one it strobes, measurably, in 16 of
18 consecutive frame pairs. At 60 fps it does not. Section 5 is the
measurement.

---

## 1. Base / Git

| | |
|---|---|
| starting SHA | `5ef311a992efbe120a3158fc7940cdc3c342dd5b` (Phase 2) |
| branch | `category3-tile-escape-v3`, created from `5ef311a` |
| worktree | `../wt-category3-tile-escape` |
| resulting commit | see section 11 |
| merged | **no**, as instructed |

No other workstream was touched. One Category 3-owned test was widened and the
reason is in section 10.3.

---

## 2. Architecture: how the physics stays out of the renderer

The brief's hardest constraint is that Godot must not become a second
simulation. It would be easy to lose: a `RigidBody2D` in the scene, or even an
honest re-implementation of the same reflection, and the video would slowly
stop being the run that was evaluated. A convex billiard has a positive
Lyapunov exponent — a one-ulp difference in the release position is a different
arena half within seconds — so "close enough" is not a category that exists
here.

So the split is data, not discipline.

### 2.1 Files

**Python — `satisfying/`** (not `tools/`; `tools/` is a declared production
root and three Company OS branch guards refuse additions to it, the same reason
recorded in `satisfying/tile_escape_cli.py`):

| file | what it owns |
|---|---|
| `tile_playback.py` | the canonical run as a JSON document, and the closed-form evaluators a renderer must match |
| `tile_cast.py` | which seeds get rendered, and what each one is for |
| `tile_readability.py` | every number in sections 4–7, predicted and measured |
| `tile_phase3_cli.py` | the driver: cast, export, stills, clip, audit, measure, verify |

**Godot — `godot/`:**

| file | what it owns |
|---|---|
| `scenes/TileEscapeRender.tscn` | the render entry point |
| `scripts/tile_escape_render.gd` | offline renderer: stills, clip, audit |
| `scripts/tile_escape_scene.gd` | the presentation layer — arena, ball, feedback, overlay |

Nothing existing was modified. `race2_render.gd`, `replay_viewer.gd` and every
other scene in `godot/` are untouched, and `TileEscapeRender.tscn` shares no
node with any of them.

### 2.2 The playback document

`satisfying.tile_playback.playback_document` turns a `TileEscapeRun` into JSON:

- **`flights`** — one record per arc: `t`, position, velocity. This *is* the
  trajectory. A renderer asked for the ball at `t` finds the last flight
  starting at or before `t` and evaluates `p + v·dt − ½g·dt²`. A closed form,
  not an integration.
- **`collisions`** — every contact including repeats, with the tile and the
  contact point. The repeats are in the document on purpose, so the renderer
  can show a bounce that is *not* progress.
- **`activations`** — the new hits alone, in order. Redundant against
  `collisions`, and present because it is what the playback audit compares
  against, and a test should not have to re-derive the thing it checks.
- **`arena`** — vertices and every tile's two endpoints in simulation units.
  Godot builds its meshes from these numbers rather than recomputing
  `polygon_arena`, so a renderer with a different trigonometric convention
  cannot draw a tile where the ball never hit.
- **`digest`** — the Phase 1 SHA-256 over the raw bytes of every collision.

Documents are 63–132 kB for the cast. JSON round-trips a double exactly
(`json.dumps` emits `repr`; Godot's `JSON.parse` reads doubles), so the
document is lossless — and
`test_json_round_trips_the_document_without_losing_a_bit` asserts it rather
than assuming it.

### 2.3 Two consequences that are the point

**The frame rate cannot change the run.** Every frame samples the same curve at
a different instant. There is no accumulated error to differ, so a 30 fps
render and a 60 fps render of the same seed are the same run at two sampling
rates — which is what makes section 5's comparison mean anything.

**A rendering bug cannot become a physics bug.** The worst
`tile_escape_scene.gd` can do is draw the right run wrongly. Section 9 lists
six times it did, including one that drew no arena at all — and in none of them
was a tile activated out of order, at the wrong time, or at all in a run that
did not activate it.

### 2.4 Why the camera is orthographic

The brief rules out the reference channel's thin concentric rings and asks for
slight physical depth. A `Line2D` cannot have depth; an extruded 3D tile can.
But a perspective camera makes the projection non-linear, and then "the arena
occupies 86% of the frame width" stops being a number Python can predict and
check.

So: orthographic, straight down −Z, `KEEP_WIDTH`. World-to-pixel is an exact
scalar, `viewport_width / camera.size`, and `tile_readability` predicts every
pixel measurement in this report from the playback document alone, with no
render. The depth comes from the **tile mesh** instead: each tile is a
chamfered slab — a large back rectangle and a smaller front one joined by four
sloped rims. Straight-on orthographic sees all four rims, one directional key
gives each a different shade, and the tile reads as a raised block. A plain
`BoxMesh` would not: its sides are exactly parallel to the view direction and
invisible.

---

## 3. The cast: eight seeds, eight jobs

Phase 2's shortlist was twenty seeds ranked by `candidate_score`. That is the
right answer to "which seed is best" and the wrong one to "which seeds should
Phase 3 render": the score's runtime component peaks at 32.5 s and falls away
either side, so all twenty completed between 30.3 s and 32.3 s. Rendering them
would test one two-second slice of the envelope and call it a proof.

`satisfying/tile_cast.py` selects by **role** instead. The sweep was rerun over
the same 50,000 seeds at 85 wu/s and reproduced Phase 2 exactly — **5,757
accepted, 11.51%** — which is also a check that nothing in Phase 3 disturbed
the Phase 2 result.

| role | seed | total | final 3 | last tile | worst body gap | last tile index / height | why it is in |
|---|---|---|---|---|---|---|---|
| `band_25_30` | **34081** | 28.09 s | 8.84 s | 3.77 s | 1.32 s | 7 / 0.14 | fast end: can the eye keep up? |
| `band_30_35` | **3530** | 32.14 s | 8.25 s | 3.82 s | 1.70 s | 50 / 0.02 | the envelope's centre; Phase 2's top seed |
| `band_35_40` | **10928** | 36.93 s | 7.42 s | 4.23 s | 2.12 s | 27 / 0.99 | slow end: does it go dead? |
| `tail_tension` | **38864** | 39.59 s | **13.90 s** | **6.20 s** | 2.27 s | 39 / 0.52 | longest final three in the accepted set |
| `smooth` | **32052** | 25.81 s | 7.58 s | 4.58 s | **0.88 s** | 42 / 0.34 | smallest worst mid-run gap |
| `final_tile_high` | **37169** | 32.16 s | 10.43 s | 4.09 s | 2.16 s | 22 / 0.92 | last tile near the top of the frame |
| `final_tile_low` | **13968** | 31.60 s | 9.61 s | 4.32 s | 1.84 s | 6 / 0.10 | last tile near the bottom |
| `contrast` | **43311** | 59.60 s | 0.52 s | **0.17 s** | **49.68 s** | 40 / 0.45 | **rejected**: the visually questionable case |

Height is the last tile's midpoint, 0 at the arena floor and 1 at its top —
a statement about the frame, where the eye has to travel, rather than about the
side index.

Runtimes span 25.8–39.6 s, last tiles 0.17–6.20 s, last-tile heights 0.02–0.99.
Every accepted role passes all twelve Phase 2 acceptance conditions.

### 3.1 The contrast case

`contrast` requires both halves of the brief's phrase. It must light all 51
tiles — the mechanic is not being slandered — and it must have failed
acceptance. Seed 43311 fails three conditions: `duration_at_most_max`,
`no_mid_run_dead_zone` and `last_tile_has_tension`. Its shape:

| milestone | 25% | 50% | 75% | 90% | 49/51 | 50/51 | complete |
|---|---|---|---|---|---|---|---|
| seconds | 2.7 | 5.4 | **57.5** | 58.7 | 59.2 | 59.4 | 59.6 |

It reaches 34 tiles in about 7 seconds and then does nothing at all for
**49.68 seconds** before finishing the remaining 17 in two. Its middle third
has a duplicate share of **1.00** — not one new tile in the middle third of the
run.

### 3.2 Two selection rules that had to be fixed, and why they are worth recording

Both were found by looking at what the first selection returned.

**Bands hug their edge.** "Highest-scoring accepted seed completing in
25–30 s" returned 30.0 s, and "35–40 s" returned 35.1 s, because the score
peaks at 32.5 s and pulls every band towards the middle. Two of the three
bands were sampling the same runtime under different labels. Each band now
names a **centre** and admits ±1 s: 27.5, 32.5, 37.5.

**An unbounded contrast case is not a contrast case.** Selecting the largest
mid-run dead zone over the whole population returned seed 45783, which lights
all 51 tiles after **1,691 seconds**. Mathematically valid, and useless: a
28-minute run says nothing about a 32-second one, and rendering it would cost
more than the rest of the cast together. The role is now bounded at 60 s.

---

## 4. Composition, measured

Exact, from the orthographic projection. Both are the same frame at two sizes,
so every fraction is identical and only the pixel counts differ.

| | delivery 1080×1920 | phone 270×480 |
|---|---|---|
| scale | 46.44 px/wu | 11.61 px/wu |
| arena width | 928.8 px | 232.2 px |
| arena height | 920.9 px | 230.2 px |
| **width occupancy** | **86.0%** | **86.0%** |
| height occupancy | 48.0% | 48.0% |
| area occupancy | 31.9% | 31.9% |
| tile length (drawn) | 48.4 px | 12.1 px |
| ball, collision diameter | 41.8 px | 10.5 px |
| ball, drawn diameter | 60.6 px | 15.2 px |
| arena top / bottom | 495.6 / 1416.5 px | 123.9 / 354.1 px |
| hook bottom | 272.8 px | 68.2 px |
| **hook clearance to arena** | **222.8 px** | **55.7 px** |
| counter clearance to arena | 148.3 px | 37.1 px |
| side margin | 75.6 px | 18.9 px |
| safe margin (5%) | 54.0 px | 13.5 px |

A 17-gon is *wider than it is tall* — its height is circumradius + apothem,
because the default orientation puts a flat side at the bottom and a vertex at
the top. In a 9:16 frame it therefore occupies a band across the middle and
leaves about a quarter of the height clear above and below. That is not wasted
space; it is where the hook and the counter go, and it is the reason a round
arena suits vertical video at all.

The hook needs no background panel: it clears the arena's top vertex by 223 px
at delivery size and 56 px on a phone, both well over its own cap height.

---

## 5. Ball readability, 30 fps against 60 fps

Phase 1 warned that its diagnostic renderer's trail strobed at higher speeds
and did not characterise it. This is the characterisation.

### 5.1 The arithmetic says it must strobe

At 85 wu/s and 46.44 px/wu the ball travels:

| | 30 fps | 60 fps |
|---|---|---|
| per frame | **131.6 px** | **65.8 px** |
| in collision diameters | 3.15 | 1.57 |
| in drawn diameters | 2.17 | 1.09 |
| frames moving more than one drawn diameter | 95.3% | 92.7% |

At both rates consecutive frames show the ball at **non-overlapping**
positions, and a sequence of non-overlapping discs is what strobing is. **No
ball size fixes this**: a ball wide enough to overlap at 30 fps would be 132 px
across, a third of the arena. The treatment has to be temporal.

### 5.2 The rendered frames say the same thing, and add a surprise

`tile_readability.strobe_report` walks the straight segment from the ball's
position on frame *n−1* to its position on frame *n*, samples **frame *n***
along it, and asks whether every sample is brighter than the arena interior. If
it is, the streak drawn on frame *n* reaches back through the whole gap and the
motion is continuous. If any sample falls to background, that dark stretch is
the strobe. Nineteen frames of seed 3530 from 8.0 s:

| treatment | 30 fps | 60 fps |
|---|---|---|
| bare ball, no halo, no trail | **16/18 pairs have a gap**, worst coverage 0.52 | 0/36, coverage 1.00 |
| halo only | **16/18 pairs have a gap**, worst coverage 0.52 | 0/36, coverage 1.00 |
| temporal trail 0.05 s | 0/18, coverage 1.00 | 0/36, coverage 1.00 |
| temporal trail 0.09 s | 0/18, coverage 1.00 | 0/36, coverage 1.00 |

Two findings.

**At 30 fps the trail is required and it works.** Sixteen of eighteen
consecutive frame pairs have a visibly dark corridor between one ball and the
next without it, and none do with it.

**At 60 fps nothing is required.** This was not expected. The emissive ball's
own bloom spreads it past its 60.6 px drawn diameter, which is enough to bridge
a 65.8 px step on its own — the halo adds nothing the bloom was not already
doing. The trail at 60 fps is a legibility choice (it shows *direction*), not a
continuity fix.

### 5.3 Choosing the trail length

The trail is a **time window**, not a frame count, so it draws the same streak
at every frame rate — which is what makes a 30 fps preview a fair preview of a
60 fps delivery. Four lengths were rendered at the same instant and compared
(`output/category3_v3/trail/compare_b_half.png`):

| window | streak | verdict |
|---|---|---|
| none | — | no direction cue, and a measured strobe at 30 fps |
| halo only | — | direction still unreadable; a symmetric glow has no orientation |
| 0.05 s | 197 px | covers the 30 fps step nominally, but alpha falls as `fade²`, so the *visible* streak is about 130 px and only just reaches |
| **0.09 s** | **355 px** | clean streak, ~230 px visible: 1.7× the 30 fps step, 3.5× the 60 fps one |
| 0.14 s | 553 px | a comet crossing half the arena; competes with the tiles |

**0.09 s.** Thirty-four samples put them 0.34 drawn ball radii apart, so they
overlap and the trail is a streak rather than a dotted line.

The trail is sampled **backwards along the canonical path**, so it bends at a
wall exactly where the ball did. A straight streak behind the ball would draw a
line through the wall on the frame after a bounce.

### 5.4 So which frame rate?

**30 fps is sufficient and is the recommendation for previews**, at half the
render cost (129 s against 233 s for seed 3530 at 1080×1920). 60 fps is
smoother in the hand and needs no trail for continuity. The decision does not
affect the simulation, the event order or the completion time — section 6.

---

## 6. Playback accuracy: rendering does not touch the physics

`--audit=1` walks every frame exactly as a clip does, saves no PNG, and records
the frame on which the scene first drew each tile lit plus the ball position it
computed at every frame. Python compares all of it against the canonical
document.

Three things have to agree, and they fail differently:

- the **order** tiles lit in — a renderer keeping its own activation set would
  scramble it;
- the **frame** each tile first appeared on — a renderer accumulating `delta`
  instead of indexing frames would be one out, and would look fine;
- the **ball position** at every frame — the trajectory itself.

The expected frame is exact arithmetic, `ceil(t_activation · fps)`, not a
tolerance.

**All eight seeds, at 30 fps and at 60 fps: 16 of 16 audits match.**

| | |
|---|---|
| activation order | matches, all 16 |
| activation frame, every tile | matches, all 16 |
| final activated count | 51/51, all 16 |
| **max ball position error** | **3.3 × 10⁻¹² world units** |

3.3e-12 wu is 1.5e-10 pixels. It is not computation error — the renderer
evaluates the same closed form on the same doubles — it is Godot's
`JSON.stringify` emitting about fourteen significant digits. The tolerance is
1e-9 wu, deliberately far below anything visual: an audit that had to allow a
*visible* tolerance could no longer tell "the renderer replayed the document"
from "the renderer computed something very close to it".

One detail that had to be got right for this number to mean anything: a Godot
`Vector2` stores **32-bit** components, so reporting the audit through one cost
5 × 10⁻⁷ wu — invisible, and a hundred times the tolerance. GDScript's own
`float` is a double, so the scene evaluates and reports in doubles and narrows
to `Vector2` only at the point of drawing.

---

## 7. Tile readability

`tile_readability.still_report` reads the rendered PNG back, samples a disc at
each tile's projected midpoint, takes the median per tile (median, not mean,
because the chamfer rims are deliberately shaded differently from the face),
and splits the 51 tiles at their largest luminance jump.

Delivery size, 1080×1920, Rec. 709 luminance 0–255:

| still | dark tiles | median dark | median lit | ratio | worst-case gap |
|---|---|---|---|---|---|
| opening (1/51) | 50 | 53.7–55.8 | 232–244 | 4.33–4.45× | 112–181 |
| half (26/51) | 24–25 | 54.5–60.5 | 207.5–208.5 | 3.44–3.81× | 81–143 |
| late (46/51) | 4–5 | 55.0–59.0 | 207.7–208.5 | 3.52–3.79× | 141–145 |
| **50/51** | **1** | **53.1–63.9** | **207.7–208.5** | **3.25–3.91×** | **143–154** |
| complete (51/51) | 0 | — | 244–255 | one population | — |

Phone size, 270×480, the measurement that actually matters:

| still | dark tiles | ratio | worst-case gap |
|---|---|---|---|
| opening (1/51) | 50 | 3.85–4.21× | 120–165 |
| half (26/51) | 24–25 | 3.29–3.59× | 79–131 |
| late (46/51) | 4–5 | 3.30–3.54× | 130–133 |
| **50/51** | **1** | **3.06–3.66×** | **131–141** |

**At 50/51, on a 270×480 frame, the one remaining tile is 3.1–3.7× dimmer than
its neighbours with a 131–141 level gap.** That is the brief's hardest
readability question and it is not close.

Three independent channels carry the distinction, so losing one still leaves
two: luminance (above), hue (cold slate against amber — opposite sides of the
wheel, so it survives greyscale), and emission with glow (the channel that
reads when a tile is twelve pixels long).

A note on the completion still: all 51 tiles are lit, so there is **one**
population and the report says so. An earlier version of the splitter always
found a boundary and described the finished arena as "50 inactive tiles at
luminance 244 and 1 active at 255", which is a measurement of nothing. Below a
30-level jump the split is now refused.

---

## 8. Hit feedback, and the duplicate problem

A new activation pulses hard: emission spikes by a factor of about 2.9 and the
slab recoils outward along its own wall normal, decaying over 0.30 s as
`1 − x²` so the tile is still visibly brighter a tenth of a second later, which
is about when the eye arrives. Outward, not inward: the ball is travelling
outward when it arrives, so recoiling away from the arena centre is the
direction the impact had.

A repeat hit on an already-lit tile gets a response that is **different in
kind, not merely in degree**: brightness only, no recoil at all, 22% of the
magnitude, and 0.10 s instead of 0.30 s. With roughly two duplicates per
activation at this operating point, a duplicate that read like an activation
would turn the progress signal into noise. `test_a_duplicate_hit_is_weaker_
than_an_activation_in_kind_and_degree` asserts both the ratio and the absence
of a push on the duplicate path.

### 8.1 Measured, on the rendered frames

Sampled 0.05 s after contact, by which time the ball is 197 px clear of the
tile but both pulses are still near peak. Seed 3530, tile 29 for the
activation and tile 43 for the repeat:

| | before | at pulse | settles to | visible change |
|---|---|---|---|---|
| **new activation** | 63.4 (dark) | 241.8 | 211.8 | **+178.5 levels, 3.82×** |
| **duplicate hit** | 207.7 (lit) | 219.1 | 207.7 | **+11.4 levels, 1.05×** |

**A duplicate produces 6% of the visible change an activation does.**

The reason that ratio is so decisive is worth stating, because it is not the
pulse doing the work: an activation is a tile going from *dark to lit*, a
178-level state change that never reverses. The 30-level pulse on top of it is
a garnish. A duplicate has no state change available to it — the tile is
already lit — so all it can offer is its own 11-level tap. The mechanic's
progress signal is structurally immune to duplicate hits, and the feedback
design only had to avoid undoing that.

### 8.2 An instrument trap, recorded because it nearly produced the wrong answer

The first version of this measurement sampled each tile at the **instant of
contact** and reported both the activation and the duplicate at luminance
255.0, with the duplicate's rise coming out 10% *larger* than the activation's
— which would have read as the feedback design failing outright.

It was the instrument. At the moment of contact the ball is against the tile,
and the sampling disc sits at the tile's midpoint, so what was being measured
was the ball's own bloom on both frames — clipped at 255 in each case, and
carrying no information about the tile at all. Moving the sample 0.05 s later,
where the ball has travelled 4.25 world units and the pulses have decayed by
3% and 25% respectively, measures the tile.

Completion is marked by shifting every tile's emission towards a paler gold
over 0.9 s, raising its energy, and turning the counter amber; the frame then
holds for 2.0 s so the complete arena can be inspected, and ends. The
elaborate escape sequence is deliberately not here — that is Phase 4.

---

## 9. What went wrong, and what each one cost

Four of these produced a wrong picture or a wrong number, and none of them
touched the simulation. That is the architecture working: every one of them was
a renderer drawing the right run badly.

**The arena was invisible.** The first render showed the hook, the counter, the
ball and its trail, and no arena at all. Two causes: the arena's vertices run
counter-clockwise, so `Basis(along, normal, +Z)` has determinant −1 for every
side and every slab's winding was reversed; and **Godot's front face is the
clockwise winding**, not the counter-clockwise one much graphics writing
assumes, so the slab's own triangles were back-facing too. Building the second
axis as `depth.cross(along)` makes the basis right-handed by construction, and
the index list was reversed. Both are now asserted.

**The ball vanished at completion.** The completion still showed a finished
arena and no ball. The run stops on completion, so the document defines the
trajectory on `[0, end_seconds]` and nowhere else; evaluating the final flight
0.6 s past that carried the ball 51 world units — several arena widths off
frame. Clamping is the honest reading: past the end there is nothing to draw.
Both the Python reference and the scene clamp, or the audit would not agree
with itself.

**Every tile was recorded as first lit on the last frame.** The audit stored
`first_lit_frame[str(tile)]` and tested `first_lit_frame.has(tile)` with the
raw int, so the membership test never matched and every lit tile was rewritten
on every change. It made the playback audit report a total failure for a
renderer that was in fact correct.

**The trail allocated 125,000 textures.** `_radial_gradient()` was called per
trail sample per frame. One 3,697-frame audit therefore built 125,000 128×128
gradient textures, ran for 28.8 s instead of 0.6 s, and took the engine down
with a stack overflow **during shutdown, after writing a perfectly good audit
file** — so the driver reported a failure for output that was correct. The
texture does not depend on time; it is now built once.

Two smaller ones: `%g` is not a GDScript format specifier (it raises, and Godot
then exits non-zero although the work is done), and Godot launched with
`--path godot` resolves relative paths against the *Godot project*, not the
repository, so the driver now passes absolute paths.

---

## 10. Tests and regression

### 10.1 Focused

`tests/test_tile_escape_phase3.py`, **50 tests, all passing**, in four groups:

- **the document** — lossless round-trip, describes the run it names, its
  evaluators agree with `TileEscapeRun`'s bit-for-bit over 400 sampled
  instants, the ball holds at the run's end, a document of another kind or
  format is refused;
- **frame arithmetic** — every activation is first visible on its own frame and
  not the one before, at 24/30/60 fps; frames never go backwards; no frame rate
  can reorder activations;
- **the cast** — selection is deterministic under input reordering, no seed
  fills two roles, every band lands within ±1 s of its centre, the contrast
  case completes every tile *and* is under 60 s, every accepted role passes all
  twelve conditions;
- **the GDScript**, read as text with its comments stripped so the tests scan
  code rather than the prose that explains it — the eight constants Python
  mirrors all agree; the scene contains no `RigidBody`, `move_and_slide`,
  `_physics_process` or `PhysicsServer`; it has no `_process` and cannot
  advance its own clock; the basis is right-handed; `_apply_ball` allocates no
  texture; a duplicate pulse is weaker in kind and degree; the renderer clocks
  on the frame index.

Plus the audit comparator, checked against a synthetic audit built from the
document: a correct audit compares clean with zero position error, and an audit
that is one frame early, one that names a different digest, one with a ball
nudged by 1e-6 wu, and one that lit the wrong number of tiles are each caught.

A last test replays every audit in `output/category3_v3/`, and skips when that
directory is absent — which it is in a fresh worktree, since `output/` is
gitignored. The evidence is checked when it exists; a GPU is never required.

### 10.2 All of Category 3

`tests/test_tile_escape.py` + `phase2` + `phase3`: **147 passed**, 0 failed.

### 10.3 The one unrelated-looking edit, and why it is not one

`test_category_three_imports_no_other_category_and_no_company_os` in
`tests/test_tile_escape.py` allowlists the stdlib modules Category 3 may
import. Phase 3's Godot driver adds `glob`, `shutil` and `subprocess` — it
finds the binary, launches it and collects the PNGs, which is what every render
driver in this repository does. The guard's purpose is the **workstream**
boundary (no race, no duel, no Company OS) and that is untouched: the list
grows when Category 3 needs another stdlib module and never when it needs
another package. The test is Category 3's own, on a Category 3 branch, and the
reason is in a comment beside it.

No cross-workstream guard was modified, skipped or xfailed. No `output/`
artefact was manufactured to make an unrelated test pass.

### 10.4 Full suite

See section 11 for the count and the baseline comparison against `5ef311a`.

---

## 11. Evidence

All under `output/category3_v3/`, which is gitignored — the repository does not
track render output, so these paths are on this machine.

| path | what |
|---|---|
| `cast.json` | the eight roles, the sweep that chose them, the acceptance rule |
| `playback/seed_<n>.json` | the canonical playback document, one per cast seed |
| `stills/seed_<n>/{a_open,b_half,c_late,d_penultimate,e_complete}.png` | 1080×1920, five progress moments |
| `phone/seed_<n>/…` | the same five at 270×480 — the mobile proof |
| `clip30/seed_3530/frame_*.png` | every frame at 30 fps, 1,025 frames |
| `clip60/seed_3530/frame_*.png` | 60 fps, frames 0–1970 (see below) |
| `preview_seed3530_30fps.mp4` | the 30 fps clip encoded, 1080×1920, 34.17 s, 2.2 MB |
| `preview_seed3530_60fps.mp4` | the 60 fps clip encoded, 1080×1920, 32.85 s, 2.6 MB |
| `holdtest/` | the completion hold at 60 fps, rendered on an idle machine |
| `feedback/{before_new,new50,quiet_n,dup50,quiet_d}/` | the frames section 8.1 measures |
| `audit/seed_<n>/audit_{30,60}fps.json` | what the scene drew, per frame |
| `strobe/fps{30,60}_{none,t0.0,t0.05,t0.09}/` | the frame pairs section 5.2 measures |
| `trail/{none,halo,t0.05,t0.09,t0.14}/` | the trail-length comparison |
| `trail/compare_b_half.png` | those five side by side at one instant |
| `nocounter/progression_no_counter.png` | the five moments at 270×480 with the counter switched off |
| `readability.json` | every number in sections 4 and 7 |

**The 60 fps clip is 1,971 of its 2,050 frames**, and that is worth stating
plainly rather than quietly re-rendering. It covers the whole run — completion
is at frame 1,929 — plus 0.7 s of the 2.0 s hold. It stopped because the
machine was saturated: the full pytest suite and several short Godot jobs were
running against the same GPU, and this render went from 127 ms a frame to no
frames at all for ten minutes while still consuming CPU. It is **not** a scene
defect, and that was checked rather than assumed: `holdtest/` renders exactly
the region it stalled in, 32.6–34.2 s at 60 fps, in 11.9 s at 127 ms a frame
on an idle machine. Nothing in this report depends on the missing 79 frames —
they are a static hold on a finished arena.

Reproduce with, in order:

```
python -m satisfying.tile_phase3_cli cast    --count 50000 --out output/category3_v3
python -m satisfying.tile_phase3_cli export  --out output/category3_v3
python -m satisfying.tile_phase3_cli verify  --out output/category3_v3
python -m satisfying.tile_phase3_cli stills  --out output/category3_v3
python -m satisfying.tile_phase3_cli stills  --out output/category3_v3 --phone
python -m satisfying.tile_phase3_cli audit   --out output/category3_v3 --fps 30
python -m satisfying.tile_phase3_cli audit   --out output/category3_v3 --fps 60
python -m satisfying.tile_phase3_cli measure --out output/category3_v3
```

`$GODOT_BIN` must point at a Godot 4 binary; the driver also takes `--godot`.

---

## 12. Candidate assessment

Not by runtime. Every one of the seven accepted seeds is readable — that is the
finding — so what follows is about which ones are *good*, and the answer does
not track completion time.

**3530 (32.14 s) — the reference.** The envelope's centre and Phase 2's top
seed. Quarter of the arena lit in 3.1 s, half in 6.9 s, never more than 1.70 s
without a new tile until 45 are lit, last three tiles in 8.25 s and the last
alone in 3.82 s. Its final tile is index 50 at height 0.02 — the arena floor,
dead centre of the bottom edge, which is the most legible place a last tile can
be in a vertical frame because it is furthest from where the eye has been
tracking the ball. The best all-round candidate.

**37169 (32.16 s) — the same shape, inverted.** Nearly identical runtime and
score, last tile at height 0.92 instead of 0.02. Worth keeping precisely
because it is the control for 3530: if the ending reads as well with the last
tile at the top as at the bottom, final-tile position is not a selection
criterion, and these two say it is not.

**38864 (39.59 s) — the tension case.** Final three in 13.90 s and a final tile
of 6.20 s, both the largest in the accepted set, against a median activation
interval of 0.42 s — the last tile takes about fifteen ordinary activations'
worth of time. This is the strongest *ending* in the cast. It is also the
longest run and reaches 90% at 24.0 s, so 40% of its length is the last five
tiles. Whether that reads as tension or as waiting is the one judgement in this
report a measurement does not settle; the 30 fps clip is the evidence to watch.

**32052 (25.81 s) — the smooth one.** Worst mid-run gap of 0.88 s, the smallest
in the cast, and only 123 collisions. It never pauses. It is also the shortest,
and its duplicate share in the final third is 0.88 — the ending is busy without
being productive. A good hook candidate, a weaker payoff.

**34081 (28.10 s) — the fast end.** Holds up. Tiles arrive quickly enough that
the arena visibly fills rather than accumulating, and the 8.84 s final three
still separates the ending from the body.

**10928 (36.93 s) — the slow end.** Does *not* go dead: worst body gap 2.12 s,
which is under the median seed's. A 37-second run is not a problem at this
operating point. Its final tile at height 0.99 is the arena's top vertex, the
hardest place to see, and section 7 says it is still found at 3.06× separation
on a phone.

**13968 (31.60 s)** is the low-final-tile control and behaves like 3530.

**43311 (59.60 s) — the contrast case, and the most instructive frame in the
set.** Its stills look *fine*. Its 46/51 frame is well composed, the five
remaining dark tiles are easy to pick out, the ball is legible. Nothing in any
still shows what is wrong with it — because what is wrong with it is that it
sits between 34 and 51 tiles for **49.68 seconds**, and a still cannot show
fifty seconds of nothing.

That is a finding about the method, not only about the seed: **still-frame
review cannot detect a pacing failure.** Composition, contrast, tile
readability and target visibility are all still-answerable and all pass here.
Pacing is not, and the thing that catches it is the Phase 2 evaluator's
`longest_body_gap_seconds`, which rejected this seed before anyone rendered it.
The two instruments are complementary and neither is sufficient.

---

## 13. The brief's inspection questions, answered

| question | answer |
|---|---|
| Is frame one understandable? | Yes. 17-gon flats read plainly, the ball is the brightest thing in frame, the hook is above it. |
| Can the eye continuously track the ball? | Yes at 60 fps unaided; yes at 30 fps with the 0.09 s trail. Measured, section 5.2. |
| Is each new tile hit satisfying enough to notice? | Yes — 2.9× emission spike plus an outward recoil over 0.30 s. |
| Are duplicate collisions visually acceptable? | Yes, and they do not read as progress: brightness only, 22% magnitude, no recoil. |
| Does progress remain obvious without a counter? | **Yes, and it was tested rather than assumed.** `nocounter/progression_no_counter.png` is the five moments at 270×480 with the counter switched off; 1 → 26 → 46 → 50 → 51 is unambiguous, and the 50/51 frame's single dark tile is findable even at contact-sheet size. |
| At 45+/51 can the viewer spot remaining targets? | Yes. At 46/51 the 4–5 dark tiles sit at 3.5–3.8× separation. |
| Does 50/51 create genuine visual tension? | Yes. One dark tile, 3.1–3.7× dimmer, 131–154 level gap, at phone size. |
| Does a run ever feel dead despite analytical progress? | Not in the seven accepted seeds; the worst body gap across the seven is 2.27 s. The rejected contrast seed does, for 49.68 s. |
| Is the arena large enough on a phone? | Yes. 232 px wide in a 270 px frame, tiles 12 px, ball 15 px. |
| Does the hook interfere with anything? | No. It clears the arena by 56 px at phone size and needs no panel. |

---

## 14. Decision gate

# VISUAL PROOF PASSED

The natural simulation at the locked Phase 2 operating point is sufficiently
readable and engaging at production speed. Nothing in the trajectory was
changed, and nothing needs to be.

The one presentation requirement that came out of the measurements:

> **At 30 fps the ball requires a temporal trail of at least ~0.05 s; 0.09 s is
> the chosen value. At 60 fps none is required for continuity.**

That is a rendering answer to a rendering problem, which is the right side of
the line the brief drew.

---

## 15. Recommendation for Phase 4 — not implemented

1. **Lock the operating point and the presentation constants.** 51 tiles,
   85 wu/s, 86% width, 0.09 s trail, amber/slate. They are now defended by
   tests in both languages.
2. **Build the climax on the completion hold.** The hold exists and is clean;
   Phase 4 replaces the 0.9 s gold pulse with the escape sequence. Everything
   before it is proven and should not be reopened.
3. **Pick the production seed between 3530 and 38864**, and pick it from the
   clips, not the stills. 3530 is the safer, better-balanced run; 38864 has the
   strongest ending and the risk that its 6.20 s last tile reads as waiting.
   That single judgement is the one thing Phase 3 could not measure.
4. **Add a pacing gate to seed selection before any batch production.** Seed
   43311 is the proof that a run can pass every compositional check and still
   be unwatchable, and that only the Phase 2 evaluator catches it.
5. **Render at 30 fps for review and decide the delivery rate separately.** It
   halves the cost, and section 6 shows the event order and completion time are
   identical either way.
6. **Audio, particles, colour grading and the final type treatment are still
   open** and were deliberately not touched.
