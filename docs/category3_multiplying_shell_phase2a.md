# Category 3, Test #2 redesign — MULTIPLYING SHELL ESCAPE, Phase 2A (visual)

**Decision: VISUAL REDESIGN PASSED**

The rejected single-ball visual was a `Node2D` drawing five concentric
polylines with `draw_line`. Every complaint against it — thin weak shells,
empty black space, a ball too small, unclear openings, weak damage, panels that
simply disappeared, repetitive layers, imperceptible near misses, a weak
payoff — followed from that one choice, and none of them was fixable by picking
better colours. This phase throws the visual language away and rebuilds the
arena as material: chamfered slabs with real depth, pillars only where a panel
actually ends, damage that starts at the impact that caused it, and a break
that fractures and retracts instead of vanishing.

The composition problem underneath all of it is arithmetic, and it is stated
first because every other decision here is downstream of it.

---

## A. Git and base

| | |
|---|---|
| Base branch | `category3-multiplying-shell-v1` |
| Base SHA | `78739b266d9c8872c350bf239ae3c60e02c7fe65` (`78739b2`, as the brief named) |
| New branch | `category3-multiplying-shell-visual-v2a` |
| Worktree | `projects/wt-category3-multiplying-shell-visual` (isolated, created for this phase) |
| Merged to main | no |
| Audio | not implemented, as the brief instructs |

Nothing in `satisfying/multishell.py`, `satisfying/multishell_playback.py`,
`satisfying/multishell_evaluator.py`, `satisfying/multishell_seeds.py` or
`satisfying/multishell_cli.py` was modified. The Phase 1 simulation, schema and
evaluator are untouched, and
`test_the_frozen_simulation_is_the_one_this_branch_was_cut_from` asserts it by
digest rather than by claim: `DEFAULT_CONFIG.digest()` is
`dcf3c2bf…8c1ea0bd` and `SCHEMA_VERSION` is
`category3-test2-multiplying-shell/2.0.0`, and the renderer refuses any
document that does not carry both.

### Files added

| file | what it is |
|---|---|
| `satisfying/multishell_visual.py` | the visual contract: framing, projection, lineage colour, and every measurement |
| `satisfying/multishell_visual_cli.py` | candidates, export, stills, clip, audit, measure, phone, report |
| `godot/scripts/multishell_scene.gd` | the scene — a playback consumer with no physics in it |
| `godot/scripts/multishell_render.gd` | the offline renderer: stills, clip, audit |
| `godot/scenes/MultishellRender.tscn` | the render scene |
| `tests/test_multishell_visual.py` | 102 tests |
| `docs/validation/category3_multiplying_shell/phase2a_candidates.json` | the committed candidate manifest Audio Phase 2B reads |

---

## B. The composition problem, as arithmetic

The arena is 49.1 world units across and the ball is 0.8 units across. **The
ball is 1.6% of the arena's width**, and no choice of frame, palette or
material changes that ratio.

The largest disc the conservative Shorts safe area permits is fixed by two
rectangles: the action rail starts at x=0.840 and the title block at y=0.840.
Centred at x=0.420 the disc's radius therefore cannot exceed 0.420 of the frame
width, and the framing that uses it lands at **0.834 of the frame width** with
the outermost shell's material 18.3 px clear of both the rail and the left
frame edge. That is the ceiling, and a fixed full-arena camera at that ceiling
draws the ball at **15 px on a 1080 px frame**. Frame one is then a speck in
the middle of five rings — which is exactly what was rejected, and it is a
property of the geometry rather than of the previous attempt's taste.

Making the ball bigger does not work either. A ball touching a panel has its
centre `ball_radius + thickness/2 = 0.55` units from the chord axis, so **1.375
is the largest draw scale that never puts the ball inside a panel it is only
touching**. The rejected version used 1.90 and was already drawing the ball
through walls. This phase uses 1.50, which overlaps by 0.05 units — 3.2 px at
the opening framing and 0.9 px at the final one, under the bloom's own falloff.

### The camera frames the frontier, not the arena

`view_radius_at` opens the framing by one shell each time the **canonical
high-water frontier** advances, read from the `shell_exit` stream and from
nothing else:

```
r(t) = r0 + Σ_k (r_k − r_{k−1}) · smoothstep((t − (t_k − lead)) / ease)
```

where `t_k` is the first canonical exit into region `k`. It is monotone by
construction — every term is monotone — it is exactly reproducible from the
document, and overlapping advances (three of the seven candidates have two
inside 0.4 s) simply sum instead of fighting over one target.

The control is rendered, not argued: `--fixed=1` pins the framing to the whole
arena for the whole run, and `output/category3_multishell_v2a/control_fixed_camera/`
holds the same nine stills made that way. Its `a_opening` is a white dot in the
middle of five rings. What the frontier framing buys, measured:

| | fixed full-arena camera | frontier framing |
|---|---|---|
| ball at frame one | 15 px | **77.2 px** |
| shell 0's opening at frame one | 101 px | **367 px** |
| ball at the climax | 15 px | 21.3 px core, **55.3 px** including halo |
| frame filled by structure at frame one | 0.287 | **1.000** |

And it is not a restless camera. Over the seven candidates it moves for
**10.4–11.7% of the run**, in at most four eased steps of 0.55 s, and the last
step lands **7.1–8.5 seconds before the escape**, so the whole climax is
rendered by a camera that has not moved. The arena's centre stays pinned to the
same point in the frame at every stage — the camera's world offset grows with
the framing precisely so that it does — so the motion is a scale about the
arena centre and never a pan across it.

### What is still empty, and why

At the final framing the arena covers **28.7% of the frame**. The largest
centred disc that fits a 9:16 frame at all covers 44.2%, and the safe area
takes the rest, so this is the geometric maximum under the gate rather than a
composition choice. The rejected 0.72-wide framing covered 22.9%.

The remaining 71% is not left black. A backdrop quad carries a radial gradient
centred on the arena and is rescaled with the framing each frame, and a second
additive pool sized from the *view radius* — not from the arena — puts the
arena's own light into the frame. At the tighter framings the vertical bands
are filled by the next shells out, which is a free consequence of framing the
frontier and one of the better arguments for it: at the opening the viewer can
see there is more out there.

---

## C. Depth, and why the camera is perspective

A wall 0.30 units thick is **5.3 px** at the final framing. Nothing drawn
inside the canonical silhouette can be made to look massive at 5.3 px, so the
mass comes from behind it.

Each panel is extruded **backwards**, away from the camera, and the camera is
perspective. A point at `z = −d` and radius `r` projects to `r·D/(D+d)`, which
is *inside* the front face, so:

* a flank can never cover a ball — every ball is at `z = 0`, in front of every
  flank — and `test_a_flank_is_drawn_inside_the_panel_it_belongs_to` asserts it
  for all five shells at all five framings;
* the projection of the `z = 0` plane is an **exact uniform scale**, because
  the camera looks straight down `−Z`, so every pixel figure in this report is
  exact rather than fitted.

The flank alone was not enough. The first render with depth showed five
identical bright hoops, because a *shaded* flank against a dark field reads as
nothing. What fixed it is lighting the **back rim** as well: each panel is now
a well seen down its own axis — a bright line at the front, a bright line at
the back, dark wall between — and **the distance between the two lines is the
depth**.

---

## D. The five layers

`PANEL_DEPTH` is `(0.90, 1.30, 1.80, 2.40, 3.20)`, inner to outer. Nothing else
about a panel may grow, because the front face is the canonical collision
silhouette. Measured at the final framing, where all five are on screen
together:

| shell | panels | open | face px | flank px | **wall px** | chord px | opening px | wall at its own framing |
|---|---|---|---|---|---|---|---|---|
| 0 | 6 of 12 | 50.0% | 5.3 | 1.3 | **6.7** | 55.1 | 101.1 | 36.5 |
| 1 | 10 of 16 | 37.5% | 5.3 | 3.4 | **8.7** | 73.3 | 138.5 | 27.7 |
| 2 | 16 of 20 | 20.0% | 5.3 | 6.8 | **12.1** | 84.3 | 161.2 | 24.7 |
| 3 | 22 of 26 | 15.4% | 5.3 | 11.6 | **16.9** | 84.6 | 162.7 | 23.7 |
| 4 | 30 of 32 | 6.2% | 5.3 | 18.9 | **24.2** | 84.8 | **79.5** | 24.2 |

The ramp is monotone and the outer wall is drawn with **3.6× the material** of
the inner one. It is also the only shell whose opening is small: 79.5 px
against 101–163 px everywhere else, and 6.2% open circumference against 50%.

**This is the difficulty story, and none of it is invented.** Phase 1 measured
first-pass rates of 95.4% → 89.3% → 67.5% → 42.4% → 15.6%; the open fraction
falls 50% → 37.5% → 20% → 15.4% → 6.2% over the same five shells. The
composition's whole job here was to stop hiding a difference the geometry
already had, and the depth ramp is what makes the fifth shell read as the
hardest before the viewer knows any numbers.

---

## E. Balls, and lineage

The founder is the only white ball. Every other ball belongs to the family of
the founder-child it descends from — `lineage[1]`, which is on every ball
record — and keeps that family's base hue for the whole run; each generation
below the family root pales it toward white by a fixed step and lifts its
emission. A founder can reproduce at most once per shell, so **five families is
the entire space**, and `test_the_palette_is_not_a_rainbow` pins it.

The families are cool jewel tones only — cyan, azure, violet, magenta, aqua —
because the warm end of the spectrum belongs to damage and breaks. A viewer
never has to ask whether an orange thing is a ball or a wound. Over the seven
candidates, **three to six** distinct tints are on screen at once, counting the
founder's white as one — so at most five family hues are ever in play together,
and usually four.

A ball is drawn as an emissive sphere at the canonical position, a dark rim
disc just in front of it, an additive halo, and a 0.16 s temporal trail.

* The **rim** is not decoration. Seven balls inside two drawn diameters happens
  — seed 7183 at 15.6 s — and seven bright discs with no rims are one blob.
* The **trail** is not needed for continuity. At a constant speed of 10 units/s
  a ball moves **0.46–0.56 of its own drawn diameter per frame at 30 fps**, so
  unlike Test #1 it never strobes. The trail is there because it says which
  ball is which inside a knot, and because it turns a pile of seven into seven
  diverging streaks. It is a *time* window, so it is identical at any rate.

### Crowding, measured properly

"Closest pair" is the obvious instrument and it is the wrong one: over twenty
seconds and fifteen balls a near-coincidence is certain, and two balls crossing
for three frames is not a glow cloud. The report clusters the balls each frame
at a one-diameter threshold and asks how long a cluster of three or more
survives:

| seed | peak | population by third | families | largest cluster | 3+ merge | blobs per ball |
|---|---|---|---|---|---|---|
| 949 | 8 | 2 → 7 → 8 | 3 | 4 | 0.03 s | 0.952 |
| 12004 | 15 | 2 → 9 → 15 | 5 | 4 | 0.97 s | 0.858 |
| 547 | 11 | 2 → 6 → 11 | 6 | 4 | 0.90 s | 0.940 |
| 11319 | 14 | 3 → 8 → 14 | 6 | 4 | 0.80 s | 0.931 |
| 3622 | 11 | 2 → 6 → 11 | 4 | 4 | 0.80 s | 0.919 |
| 12818 | 15 | 4 → 9 → 15 | 6 | 4 | 0.17 s | 0.950 |
| **7183** | 13 | 3 → 10 → 13 | 5 | **8** | **1.63 s** | 0.875 |

Six of the seven never get past a four-ball cluster and never hold a three-ball
merge for a second. **Seed 7183 is the stress case and it is a real pile, not a
chain**: at 15.6 s, balls 4–10 are inside a box about two and a half drawn
diameters across, and they stay that way for 1.63 s. It is recorded here rather
than hidden, and it survives because it is also the most evenly mixed route in
the whole Phase 1 shortlist (21 opening crossings to 20 breaks) and because the
rule that produced the set is not allowed to have exceptions. A production
phase choosing one seed should know that 7183 is the one that tests the
presentation hardest.

Population escalation reads without a counter in all seven: the last third is
**3.8× to 7.5×** the population of the first third, and every run goes
1 → 2 → several → many.

---

## F. Damage, and the break

The five canonical states are read from `panel_states` and never re-derived by
accumulating the `damage` stream. `test_a_panel_is_drawn_in_the_state_its_ledger_gives`
checks the transitions in both directions and checks that a broken panel stays
broken to the end of the run.

| state | what is drawn |
|---|---|
| `healthy` | a lit face and a lit back rim, cool; the panel's own material |
| `damaged` | two marks at the panel's **actual first two impact offsets**; the face begins to lose its sheen |
| `critical` | four marks, warmer and brighter, plus a local stress glow around the panel |
| `fractured` | six marks; the three sub-slabs open two real gaps and roll 9° about their own long axes; the face is nearly dull |
| `broken` | the panel is gone, the passage is open, and the pillars either side keep a warm cast for the rest of the run |

A designed opening is posted **cool** and a broken one **warm**, and they stay
that way, so late in a run a viewer can tell a doorway from a wound without
having seen the break happen. A pillar that is both — one that already flanked
an opening before the panel beside it went — keeps its cool cap, because
marking the doorway is the more useful of the two readings.

Three things are worth naming because each was a wrong answer first.

**The body is never recoloured.** The first render put the damage emission on
the panel body, and forty panels came out a flat orange-brown at `damaged` —
precisely the thing the brief forbids. The body now only ever goes white-hot,
only at a break, and only for 0.16 s. Everything else is the marks, the stress
glow and the face's own sheen. A worn panel loses its lustre before it gains a
crack, which is a reading a viewer gets without being told.

**A mark spans the wall, not the face.** A hairline across a 5.3 px face is
invisible. Each mark is exactly as thick as the panel radially and as deep as
the panel behind it, so it reads on the face *and* down the flank: 5.5 px wide
and 24 px tall on an 85 px outer panel. Marks sit at `panel_local_offset` from
the canonical collisions, in the order they happened, so damage originates at
the impacts that caused it.

**The fracture gap had to be twenty times bigger than it looked.** 0.05 units
is 0.9 px at the final framing. It is now 0.20 units — 3.5 px at the final
framing, 13 px while its own shell is framed — and the gaps are *cut out of*
the sub-slabs rather than made by pushing them apart, so the panel's two ends
stay exactly where they were and a fractured panel never occupies a pixel a
healthy one did not.

The break itself is four things on one canonical `panel_break`: a 0.16 s
white-hot flash, a shockwave ring, eight debris sparks whose directions come
from a hash of the panel's own identity (so two renders throw the same debris),
and a 0.55 s retraction of the three sub-slabs into the flanking pillars. The
passage is clear when it finishes and nothing is left to clutter it.

Over the seven candidates every state is reached many times — 27–41 `damaged`,
15–24 `critical`, 7–15 `fractured`, 18–38 `broken`, with **9–18 breaks paid for
by more than one ball** — and the smallest panel to change state anywhere is
55.1 px long.

---

## G. Openings, pillars and near misses

**A pillar exists only where a panel actually ends.** A pillar is the panel
capsule's own round cap, so a vertex with open slots on both sides has no
material there at all; the first render drew a line of disconnected dots
floating in every opening. A pillar that flanks an opening — the one a ball
clips when it aims at the hole and misses — carries a cool cap and 1.35× the
depth of an interior one. That is what makes an opening read as a doorway with
two posts rather than as an absence.

No arrows and no explanatory text are used anywhere, and the render draws no
text at all. The geometry carries it: at the final framing the narrowest
opening in the arena is 79.5 px against a 21.3 px ball, a ratio of 3.7, and
`test_an_opening_is_bigger_than_the_ball_that_has_to_thread_it` holds every
shell to at least 2.5×.

A near miss reinforces the canonical `near_miss` event and only that: a spark
at the ball's recorded position and a hot rim on the two flanking pillars, for
0.16 s, with the brightness scaled by `arc_separation_ball_radii` so a closer
miss sparks harder. No trajectory is faked and there is no slow motion
anywhere in this phase.

---

## H. The climax, and the two endings

There is no invented unlock. The climax is what the physics produces: many
descendants, an arena visibly worn through, and the one wall that is 6.2% open.
On the canonical `escape` the escaping ball's halo flares 3×, a shockwave ring
sweeps out past the arena, and **the other balls keep running** — the brief's
instruction not to obscure continued activity is the reason the effect is one
ring and one flare rather than a global freeze.

The document ends *at* the escape, so the two endings the brief asks to be
compared are:

* **Hard cut** (`--release=0`): the last frame is the escape instant.
* **Release beat** (`--release=0.55`, the default): only the escapee runs on,
  along its own canonical flight. Every other ball holds at its last canonical
  position rather than being extrapolated — a ball still inside the arena has
  walls in front of it and continuing its flight would draw it through one —
  and the shells hold with them, because a shell that kept rotating against a
  frozen ball would sweep a panel through it. So the beat is the whole arena
  stopped on its true final state with one ball still leaving it. That is a
  stylisation, and it is the only one in the phase; nothing in it is
  fabricated.

Both were rendered for seeds 12818 and 7183 and compared frame by frame off
the encoded clips. **The release beat is stronger**, and the comparison says so
rather than the reasoning: on the hard cut the escape lands on the last frames,
the shockwave ring has barely started when the video ends, and the final split
is not visible at all. On the release beat the ring completes its sweep past
the arena and the escapee and its newborn child visibly separate into two
trajectories outside the wall. The hard cut ends *on* the payoff; the beat ends
*after* it.
The reason is specific rather than general: in **all seven** candidates the
final shell crossing *is itself a reproduction* — `first_for_ball` is true, so
the mechanic fires one last time on the way out — and the last thing that
happens is one ball becoming two outside the arena. Seed 12818's founder spawns
ball 14 at 22.75 s and the escape is recorded at 22.84 s, 0.09 s later. On a
hard cut that split is two or three frames. With 0.55 s the viewer sees it. The beat is deliberately
short; nothing is extended aimlessly, and the whole ending is 0.95 s including
the hold.

---

## I. The candidate set

`CANDIDATE_RULE` is the brief's own filter applied to the **eighteen Phase 1
shortlisted seeds and to nothing else**. No new seed search was run. Seven of
eighteen survive: 20–24 s of runtime, first split at 2.5 s or sooner, final
population 8–15, no Phase 1 flag.

| seed | duration | first split | balls | gens | escape route | escaping ball | opening / break |
|---|---|---|---|---|---|---|---|
| 949 | 20.16 s | 2.31 s | 8 | 5 | opening | descendant (g3) | 18 / 4 |
| 12004 | 21.71 s | 2.40 s | 15 | 5 | opening | descendant (g2) | 29 / 12 |
| 547 | 21.73 s | 2.25 s | 11 | 4 | opening | founder | 31 / 3 |
| 11319 | 21.80 s | 1.47 s | 14 | 5 | break | founder | 30 / 23 |
| 3622 | 22.82 s | 0.45 s | 11 | 5 | break | descendant (g3) | 31 / 5 |
| 12818 | 22.84 s | 0.50 s | 15 | 5 | opening | founder | 28 / 16 |
| 7183 | 23.21 s | 0.62 s | 13 | 5 | break | descendant (g3) | 21 / 20 |

Four escapes through an opening and three through a break; three founders and
four descendants; populations 8 to 15; opening-dominant routes (949, 547, 3622)
and break-heavy ones (11319, 7183). The set is **not ranked** and no production
seed is selected — that is a later phase's decision.

The manifest is committed at
`docs/validation/category3_multiplying_shell/phase2a_candidates.json` and
carries the rule, the seeds, the Phase 1 digest of each run and the render
config digest, so **Audio Phase 2B can re-derive the list rather than trust
it**, and a seed that has quietly become a different run fails loudly.

---

## J. The renderer changed nothing

The architecture's claim is that a consumer may read a trajectory and may not
compute one. `multishell_visual_cli audit` turns that into a diff: Godot walks
every frame a clip would walk, writes down the ball positions and panel states
**the scene itself computed**, and Python compares them against
`satisfying.multishell_playback`.

| | |
|---|---|
| seeds × rates | 7 × {30, 60} fps |
| frames walked | 13,900 |
| panel-state rows compared | 1,167,600 |
| **panel-state mismatches** | **0** |
| **worst ball position error** | **5.414e-13 world units** |
| per-seed error, 30 fps vs 60 fps | bit-identical for six of seven seeds |

The residual is JSON round-trip precision, not computation. Getting there cost
one known trap: **a Godot `Vector2` is 32-bit**, and reporting the audit through
one read 1.18e-06 — a million times the arithmetic the scene actually does.
GDScript's own `float` is a double, so the audit path never narrows;
`_position_pair` returns doubles and `_position_row` narrows only for a
transform. A test asserts that `audit_state` uses the former.

That the two rates agree is the second half of the proof: the scene has no
`_process`, no accumulated delta and no random source, so **the frame rate
cannot change the run**. Six of the seven seeds report a bit-identical worst
error at both rates. The seventh, 11319, reports 4.274e-13 at 30 fps and
4.283e-13 at 60 — not a disagreement but a consequence of sampling: 60 fps
walks every instant 30 fps walks and twice as many besides, so its maximum is
taken over a strictly larger set and can only be the same or larger. Both are
at the floor of a double round-tripped through JSON.

---

## K. Tests

`tests/test_multishell_visual.py`, **102 tests**, in four groups.

* **The consumer contract.** The scene is parsed as text and asserted against:
  no `RigidBody`, no `CharacterBody`, no `move_and_slide`, no
  `_physics_process`, no `PhysicsServer`, no `randf`/`randi`, no `_process`.
  The Python module is asserted never to import the simulator. Every effect in
  `_read_events` is keyed to an event kind that exists in the canonical schema,
  and four invented ones are asserted absent.
* **The shared constants.** Fifty-four numbers and six ramps are read out of
  the GDScript and compared with the Python copy that predicts every pixel
  figure in this report. This test has already earned its place: it caught
  `SHELL_ALBEDO_VALUE` drifting between the two copies during a look pass.
* **The event mapping.** Panel states against the ledger in both directions,
  damage-mark offsets inside the panel they are on, framing changes only at
  canonical `shell_exit` times, still moments inside the effect window of the
  event they name, and the ending extending only the ball that escaped.
* **The composition.** The safe area as a gate, the 0.834 framing derived from
  the rail and the title block rather than asserted, the ball's draw scale
  against the contact distance, the monotone wall ramp, every opening wider
  than 2.5 balls, and the crowding thresholds.

Two more assert things that are easy to lose: `_oriented_basis` builds the
second axis as `z.cross(x)` (a mirrored basis reverses every winding and
backface culling removes the whole slab — Test #1 rendered an arena with none
of its fifty-one tiles visible before this was found), and no per-frame
function constructs a texture, material or mesh (Test #1 made 125,000 gradient
textures in one audit and crashed the engine during shutdown).

**Category 3 regression, on this branch:** `tests/test_multiplying_shell.py`,
`tests/test_shell_escape.py`, `tests/test_tile_escape*.py` and the new file all
pass — 216 for the two Test #2 files and the new one together.

One of them earned its keep during this phase.
`test_category_three_imports_no_other_category_and_no_company_os` holds
everything under `satisfying/` to the standard library, numpy, Pillow, three
leaf `audio/` modules and itself, and it caught the first version of
`multishell_visual_cli` importing `rendering.encode` for a nicer encode
command. The encode is now twelve arguments inside the CLI. That boundary is
what lets Category 3 be lifted out whole, and it is worth more than the twelve
arguments.

**Full suite:** `18 failed, 6272 passed, 441 skipped` in 39 minutes.

Eighteen is the recorded baseline for this repository and these are the
recorded eighteen: twelve stale cross-workstream branch guards, and six tests
that open an absent `output/sloped_race_v1/cameras_v221_5432.json`. The branch
guards compare the working tree against an old branch point and complain about
`.gitignore`, `ai_platform/`, `company/`, `audio/asmr.py` and hundreds of other
files from workstreams this branch has never touched. Two of them list this
phase's files inside that complaint — alongside Phase 1's own
`satisfying/multishell*.py`, which were already present at the base commit —
which is exactly what makes them stale rather than informative. **No test fails
on this branch that does not fail without it**, and the count is unchanged.

---

## L. Outputs

Everything is under the un-gitted `output/category3_multishell_v2a/`.

* **Review MP4s**, 1080×1920 at 30 fps, one per candidate, plus hard-cut
  variants for 12818 and 7183: `review/multishell_seed<N>.mp4`.
* **Event-centred stills**, nine per candidate, each taken at a canonical event
  time plus a stated offset rather than at a round number of seconds:
  `a_opening`, `b_first_split`, `c_four_balls`, `d_near_miss`,
  `e_damaged_panel`, `f_critical_panel`, `g_panel_break`, `h_late_population`,
  `i_final_escape`.
* **Phone-sized stills** at 405×720, the width a Shorts player lays out
  against, downsampled with Lanczos: `phone/seed<N>/`.
* **Measurements**: `phase2a_measurements.json`, carrying the render config and
  its digest beside every number.
* **The audit**: `audit/audit_report.json`.
* **The fixed-camera control**: `control_fixed_camera/`, the same nine stills
  with the framing pinned to the whole arena.

Seven stills are committed at half resolution under
`docs/validation/category3_multiplying_shell/phase2a_stills/` — the opening,
the first split, a break, the late population, the escape, a fractured panel
and the fixed-camera control — so the claims in this report can be checked from
the repository alone. The full-resolution set stays in the un-gitted output
directory.

The review clips are encoded at CRF 16, preset `slow`, with `-bitexact` and no
metadata, so two encodes of the same frames compare byte for byte. The encode
command is twelve arguments inside `multishell_visual_cli` rather than a call
into `rendering/encode.py`, because `satisfying/` is held to the standard
library, numpy, Pillow and three leaf audio modules by
`test_category_three_imports_no_other_category_and_no_company_os`. That guard
caught the first version of this CLI reaching into `rendering/`, which is
exactly what it is for: Category 3 is meant to lift out whole.

### At phone size

1080×1920 is the render, not the viewing condition. At 405×720 — 0.375 of the
render — the ball is 29.0 px at the opening and 8.0 px core / 20.7 px including
halo at the climax; the outer wall is 9.1 px against the inner shell's 2.5 px;
the narrowest opening is 29.8 px. The late-population frame still resolves
fourteen distinct balls in distinct hues. What does *not* survive the
downsample is telling `damaged` from `critical` at a glance — "worn" against
"healthy" does, the specific step does not. That is a fair limit to record
rather than a failure: the damage ramp's job in the video is escalation, and
the step a viewer has to see is the break.

No production master was made, as the brief instructs.

---

## M. Bounds on this proof

Three, stated plainly.

1. **Nobody has watched the clips at full speed on a phone.** Everything here
   is measured from the document, from the projection, or from frames read back
   out of the encoded clips — including contact sheets across each run and
   consecutive-frame strips through the camera transitions, which is how the
   framing was checked for continuity. That is not the same as watching
   twenty-two seconds at speed, and whether it is *satisfying* is a judgement
   no still can make. Test #1's Phase 3 found the same limit from the other
   side: its contrast seed's stills all looked fine and the run had a
   fifty-second hole in it.
2. **Seed 7183's 1.63-second seven-ball pile is presentation-limited, not
   presentation-solved.** The rim, the hue separation and the trail are what
   keep it countable, and the report measures the pile rather than claiming it
   away. If a production phase wants that seed, that moment is the one to watch.
3. **The frontier framing is a departure from "fixed camera preferred".** It is
   here because the fixed alternative fails frame one by arithmetic, not by
   taste, and the §B table plus the rendered control are the evidence. It is
   four eased steps totalling about 11% of the run, no pan, and a climax
   rendered by a still camera. The fixed version is not hypothetical — it is in
   `control_fixed_camera/` and committed as
   `phase2a_stills/control_fixed_camera_a_opening.png` — so a reviewer who
   prefers it can take it. The ball is 15 px in frame one there, and stays
   there for the whole run.

---

## N. Decision

**VISUAL REDESIGN PASSED.**

Against the brief's own list: frame one reads bright ball → strong physical
shells → obvious escape gaps, with the ball at 77 px and shell 0's openings at
367 px; the arena fills the useful frame at every framing and the empty space
is at the geometric minimum the safe area allows; the balls are heroes with a
coherent five-family lineage palette and no rainbow; the five layers differ by
a monotone 3.6× wall ramp and a 50%→6.2% openness fall, so the outer shell
reads as the hardest barrier before the viewer knows the numbers; the walls
have real mass; the openings are unmistakable and posted; the five damage
states are a coherent progression that never recolours a panel; a break
fractures, throws debris and retracts into its pillars, leaving a clean
passage; 1 → 2 → several → many reads without a counter in all seven
candidates; near misses spark at the pillar the ball nearly clipped; and the
climax is the physics' own, unobscured, with a 0.55 s release beat that exists
because the last crossing is usually itself a split.

The safe area passes as a gate with 18.3 px of clearance and zero frames of
hidden ball. The renderer is proven not to have touched the simulation at 30
and 60 fps across all seven seeds.

No production master, no audio, not merged.
