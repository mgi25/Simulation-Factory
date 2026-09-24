# Category 3, Test #2 — two-team multiplying shell race
## Phase 4B: camera, scale and destruction

A human watched the Phase 4A review clips and rejected the presentation. The
mechanic survived the review intact — cyan against orange, two founders, same
colour cloning, a growing population, harder outer shells, shared persistent
damage, a real winner, a procedural score. Nothing in this phase touches any of
it. The simulation's config digest is still
`4a3ab8ba22ae7c54981700823cc5b4eaf147c72fc5ab609a244d9cbaeb6ce572`, the schema
is still `category3-test2-two-team-shell-race/3.0.0`, the three review
candidates still produce the same winners by the same routes, and the audio
masters re-render **byte-for-byte identical** to Phase 4A's — SHA-256
`7e79e90f507a2c7c…`, `62608199c9bdc5a1…` and `f038a1a9b3305724…` against the
files the v4a worktree still holds, not merely the same loudness figures.

What the review rejected was everything around that: a camera that retreats
four times, an arena that ends up small in a tall dark frame, damage that looks
like annotation rather than injury, a break that reads as a marker vanishing,
and a hook that fades to a ghost instead of leaving.

**Base.** `category3-two-team-shell-race-v4a` at
`b9882392b8e0d65408e1392c27e73d3d433c9899`. Branch
`category3-two-team-visual-impact-v4b`, worktree `wt-category3-two-team-v4b`.
Not merged; no production master.

Render config digest `dfe8208b31d717b6` — every constant the renderer draws
with, hashed, so a still in this document can be tied to the settings that made
it after the fact.

---

## 1. The camera was solving the wrong problem

Phase 4A's framing rule was: *take the largest centred disc that clears the
Shorts action rail*. That gave `FRONTIER_WIDTH_FRACTION = 0.652` and a
whole-arena clearance of 15.12 px, and the phase document presented the 15.12 px
as the binding constraint — the arena was as large as it could possibly be.

It was as large as *that rule* allows. The conservative action rail begins at
x = 0.840, so the horizontally centred band that clears it is 0.680 of the frame
width. Any rule of that shape caps the arena below 0.68 for ever, whatever else
changes. The review's "the simulation becomes too small in the vertical frame"
and "there is too much empty dark space" were not tuning failures; they were the
rule working exactly as designed.

The brief replaces the rule. Cropping is allowed, the viewer does not need to
see every shell at all times, and the objective is that the interesting action
is large. So the question becomes: *what does the viewer actually need to see,
and is that visible?*

### `critical_visibility_report` — the measurement that replaced the number

Every instant at which something specific must be visible is a canonical event,
so the check is per-event rather than per-arena. Five classes: the first clone,
every panel break that some ball later used as a passage, every strong near
miss, every frontier crossing, and the winning escape. Three of them are hard —
a clone, a passage break or the payoff behind the player's controls is a
rejection — and a frontier crossing on the far side of the outer ring is not.

| fraction | hard classes | hidden (17964 / 3762 / 1176) | worst escape cover | worst passage-break cover | worst clone cover |
|---:|:--|---:|---:|---:|---:|
| 0.652 | pass | 0 / 0 / 0 | 0.000 | 0.000 | 0.000 |
| 0.800 | pass | 1 / 0 / 0 | 0.000 | 0.000 | 0.000 |
| **0.850** | **pass** | 2 / 0 / 0 | **0.000** | **0.000** | **0.000** |
| 0.900 | **FAIL on 3762** | 2 / 2 / 0 | **0.435** | 0.000 | 0.000 |

**0.900 is rejected on evidence, not taste**: on seed 3762 it puts 43.5% of the
winning escape under the action rail. That is the one thing that may never be
behind the player's controls.

The hidden subjects are frontier crossings on 17964 and nothing else: one of
its 78 at 0.800, two at 0.850, the worst fully covered — the arc the review
agreed to spend. Every break that became a passage (19 on 17964, 5 on 3762, 9
on 1176), every first clone and every winning escape is 0.000 covered at 0.652,
0.800 and 0.850 alike. The breaks that *do* fall under the rail are ones no ball
ever went through.

### The rendered comparison

Eleven event-centred stills of seed 17964 at four fractions, measured off the
pixels (`tools/two_team_phase4b_lab.py sweep`). **The sweep varies the frame
fraction and nothing else** — the 0.652 row is the Phase 4A *framing* with
everything else 4B, not Phase 4A, so it isolates what the fraction alone buys.
The Phase 4A wall at its own depth ramp was 23.78 px, not 35.7.

| fraction | mean ink | worst empty band | drawn ball | final opening | final wall | hidden |
|---:|---:|---:|---:|---:|---:|---:|
| 0.652 (4A framing) | 0.398 | 579 px | 26.0 px | 27.6 px | 35.7 px | 0 |
| 0.800 | 0.471 | 544 px | 31.9 px | 33.8 px | 51.4 px | 1 |
| **0.850** | **0.490** | **531 px** | **33.9 px** | **35.9 px** | **57.2 px** | 2 |
| 0.900 | 0.508 | 518 px | 35.9 px | 38.1 px | 63.3 px | 2 |

The fraction alone buys 30% more ball, 30% more opening and 60% more wall, for
one extra partly covered crossing on one candidate out of three — 0.800 already
costs one. 0.900 buys another 6% and loses the payoff. **0.850 selected.**

Contact sheets: `docs/validation/category3_two_team_shell_race_v4b/framing/`.

---

## 2. Two moves, not four, and the grouping is forced

Phase 4A moved the camera once per shell, because the schedule was a function
of the shell list. The brief asks for two or three transitions instead. The
answer is not a preference — two rules from the review pin it down completely:

1. a ball may never be outside the frame, so the framed extent is at least the
   frontier region at every instant;
2. the outermost shell may not be revealed before the race reaches it.

Rule 2 fixes the last stage at trigger region 4, extent shell 4. Rule 1 then
requires some stage to cover frontier regions 2 and 3, so its extent is at
least shell 3; taking it to be exactly 3 is what avoids a fourth stage. The
opening covers regions 0 and 1 for the same reason — region 1 is reached 0.52 s
into 17964, and a reframe there is a camera move in the first half second for
no story reason.

    CAMERA_STAGE_PLAN = ((0, 1), (2, 3), (4, 4))      # (trigger region, extent shell)

This is the only two-transition grouping that satisfies both rules, and the
requirement that the final wall be framed when the winner leaves through it
forbids dropping to one.

| seed | stage 1 | stage 2 | lock | static tail | zoom range |
|---:|:--|:--|---:|---:|---:|
| 17964 | 4.63 → 5.08 s (trigger 4.77) | 21.17 → 21.62 s (trigger 21.31) | 21.62 s | 4.16 s | 1.933x |
| 3762 | 8.29 → 8.74 s (trigger 8.43) | 18.69 → 19.14 s (trigger 18.83) | 19.14 s | 4.98 s | 1.933x |
| 1176 | 11.96 → 12.41 s (trigger 12.10) | 18.11 → 18.56 s (trigger 18.25) | 18.56 s | 5.21 s | 1.933x |

**Grouping the opening onto shell 1 is most of the gain before the frame
fraction is touched at all.** The camera's total zoom range falls from 2.80x to
1.933x, so the late arena is 45% larger *relative to the opening* than it was.
The middle stage then holds one fixed framing for 16.08 s — 62.4% of 17964's
run — while the population grows from 5 to 12, and the final stage holds
another 4.16 s while it reaches 18. That is the direct answer to "action
visually loses intensity while simulation activity is actually increasing":
for most of the video the scale no longer changes at all, so what the viewer
sees getting busier is the race.

### Event protection, and the bug it exposed

A zoom may not run across the first clone, a panel break, a strong near miss
(≤ 0.75 ball radii) or the escape. The first implementation pushed a blocked
move to just after the last guard in its window.

**That put balls outside the frame.** On 17964 it delayed the final reframe by
0.56 s; the stage it was still holding is framed on shell 3 while the race had
already entered region 4, and ball 7 spent 63 frames off-screen. On 3762 the
same rule cost 98 frames. The trigger *is* the instant the old framing stops
being big enough, so there is no slack after it to spend.

Protection now pulls a move earlier and never later. `containment_report`
measures it rather than asserting it: worst ratio of a ball's drawn extent to
the nearest frame edge is 0.307, 0.254 and 0.269 on the three candidates, and
zero frames of 1548, 1449 and 1427 have a ball outside.

Where no earlier slot exists the move proceeds and the report names what it
could not avoid. On these three candidates that is 2, 3 and 1 conflicts, every
one a near miss or a break sitting between 0.24 s before and 0.45 s after the
crossing that triggered the move — which is to say, caused by it. **None is ever the first clone, a passage break or the
escape** — those are protected structurally by the schedule, with seconds of
margin, and there is a test for it.

### The transition duration, and a gate the brief forced open

Two transitions instead of four is the same total zoom in half as many
payments. Phase 4A could hold "a reframe never moves the screen faster than a
ball does" because its largest single step was 1.45x; 4B's first step is 1.62x.
The two requirements are arithmetically incompatible, and keeping the old
number would have meant keeping the camera the review rejected.

So the ease was swept against the measurement rather than chosen. Worst screen
velocity as a multiple of the ball's own, on all three candidates:

| ease | 0.25 s | 0.30 s | 0.35 s | 0.40 s | **0.45 s** |
|---|---:|---:|---:|---:|---:|
| ratio | 2.81x | 2.38x | 2.06x | 1.81x | **1.61x** |

0.45 s is the slowest the brief's 0.25–0.45 band allows, costs 0.10 s of static
tail, and containment holds at every value. The gate is now stated: 2.0x, which
is loose enough for a candidate whose frontier advances sit closer together than
these three and tight enough that 0.30 s or a single-transition schedule fails
it.

---

## 3. The final wall, and the cage nobody had noticed

`PANEL_DEPTH` goes from `(0.70, 1.15, 1.75, 2.55, 3.60)` to
`(0.70, 1.25, 2.15, 3.60, 6.20)`, per-shell chamfers replace the single value,
and the larger frame fraction brings the camera in from 65.8 to 50.5 world
units. Nothing at z = 0 moves: the front face is still the canonical collision
silhouette on every shell, and all of the added mass is behind it.

Apparent thickness at each phase's own final framing, face plus flank, in
1080-wide pixels:

| shell | 0 | 1 | 2 | 3 | 4 |
|---|---:|---:|---:|---:|---:|
| Phase 4A | 6.96 | 8.74 | 11.78 | 16.58 | 23.78 |
| **Phase 4B** | **9.57** | **13.04** | **19.96** | **32.79** | **57.20** |

The final wall is 2.41 times as thick as it was and 5.98 times the innermost
shell, where 4A managed 3.42. `test_the_wall_depth_ramp_is_what_the_report_says`
recomputes all ten numbers from the frustum rather than comparing two copies of
one constant.

**And then the first render showed the wall as a comb you could see through.**
`POST_DEPTH_FACTOR` was 1.55 — a pillar is a cylinder pointing at the camera,
and at 1.55 times the panel depth the outer shell's pillars were 9.6 world units
long and projected as 66 radial spikes reaching inward. It was there in Phase 4A
too, hidden by a camera half the size; deepening the ramp is what made it
obvious. At 0.55 the pillar ends well inside the panel's own depth and reads as
what it is, the seam between two blocks, and the wall reads as a solid segmented
band. That is the "structural segmentation" the brief asked for, and it cost one
constant.

At the final framing the outer opening is 35.9 px against a 33.9 px drawn ball
and a 26.1 px collision ball — 1.38 ball diameters of gap. The viewer can put
the two side by side and see that it is barely enough.

---

## 4. Damage that happens to the material

The 4A marks were up to six identical bright bars at the first six impact
offsets, at up to 4.0 emission on an unshaded material — a row of lit markers
lying on a wall, which is what the review called "UI annotations".

A wound is now four parts: a dark unlit chip where the material went, a bright
hairline inside it, and two branches that only appear once the panel is
critical. Each part runs from just in front of the face back into the wall, so
it protrudes through the inset flank and is read on the flank too.

**Where.** Impacts land at the canonical `panel_local_offset`. Two impacts
within `DAMAGE_CLUSTER_CHORD` are the same wound and the second deepens the
first — the chip grows 34% per extra hit, capped at 2.10x. The merge distance
was swept, not chosen: at half a ball radius only 2 to 7 panels per run end up
with two distinct wounds and none ever has three, which loses the "multiple
connected cracks" the critical state is supposed to read as; at a quarter of a
ball *radius* (0.13), 13 to 18 panels have two wounds, the maximum is three,
and the heaviest single wound still absorbs 9, 12 and 19 impacts. Across the
three candidates, 335 to 442 impacts resolve to 131 to 160 wounds.

The emission ramp is halved, because the bright part of a wound is now a
hairline in the bottom of a pit rather than a bar on a face. A crack is a
rectangle rolled by 34 degrees and its rotated radial extent is
`span·cos(tilt) + (width/thickness)·sin(tilt)`; at 34 degrees that stays inside
the panel for any span up to 1.128, so `DAMAGE_CRACK_SPAN = 1.10` is the longest
crack that never puts a pixel outside the canonical silhouette.

### The final wall was pristine, and a canonical field was being thrown away

The brief sets one hard gate: a still from the final struggle must communicate
many balls, a substantial barrier, a visibly difficult opening, accumulated
damage, and where the next escape could happen. **It failed on the fourth.**
At the final-wall moment the outermost shell is

| seed | outer shell at the final struggle |
|---:|:--|
| 17964 | 64 healthy, 2 damaged |
| 3762 | **66 healthy — not one mark on the barrier** |
| 1176 | 64 healthy, 1 damaged, 1 broken |

which is the Phase 4A finding restated: the final wall's threshold is about
eighteen ordinary hits on one panel, so in half the review candidates no panel
of it ever visibly cracks. The physics is frozen, so it cannot break sooner.

It does not have to. `damage` events carry **`fraction`** — the panel's
cumulative damage over its own threshold — on every single collision, and Phase
4A read only the quantised five-state ledger. A panel at 0.35 of its threshold
was drawn identical to one nothing had ever touched. Reading `fraction` is
reading the document, not inventing a state:

| seed | outer panels carrying wear | worst fraction | scuffed (≥ 0.04) | sheen dimmed |
|---:|---:|---:|---:|---:|
| 17964 | 15 | 0.346 | 8 | 13 |
| 3762 | 28 | 0.233 | 19 | 28 |
| 1176 | 3 | 1.019 | 1 | 1 |

A worn panel loses its sheen continuously and takes a scuff — the chip alone,
no crack — at its heaviest wound. 3762's final wall goes from nothing to
nineteen marked panels. The scuff is scaled by the *square root* of the wear,
because a chip is 7.4 px wide at the final framing and a linear scale would put
a 0.07-wear panel at 0.4 px, which is not worth drawing.

This is what the Phase 4A comment already said the design wanted — "a worn
panel loses its sheen before it gains a crack" — and what quantising to five
states prevented.

### `Basis.scaled` shears an oriented basis, and I wrote the bug anyway

The chip is scaled along the panel's chord by how worn the wound is, and the
first version did it with `basis.scaled(Vector3(growth, 1, 1))`. `Basis.scaled`
multiplies the basis's **rows**, which are the global axes, so that stretches a
diagonal panel's chip along world X rather than along its own chord — a panel
at 45° gets a chip pointing the wrong way.

Phase 4A already found this on the panel slabs and left the warning in the
comment two hundred lines above; I wrote it again regardless, and only caught it
on a re-read of my own diff rather than from a render, because a small chip's
shear is not obvious on a still. `_oriented_basis` pre-scales the columns and is
the only correct form. `test_the_scene_never_scales_an_oriented_basis` now
asserts that every `.scaled(` in the scene is on `Basis.IDENTITY`, where rows
and columns are the same thing — so the next person cannot reintroduce it.

**The scene's own wounds are now audited against the derivation, not against a
second copy of the rule.** `audit_state` emits what the renderer actually built
— its camera stages, its view radius, its clusters, its wear and its passage
responses —
and `multishell_visual_cli audit` diffs them against what `multishell_visual`
derives independently from the same document. On 17964 over 774 frames: view
radius agrees to 3.8e-13, stage times to 1.1e-14, all 160 wounds match by
identity and to 5.0e-16 in offset and growth, every panel's wear agrees
exactly, and the structural counts match.

That is the Phase 4A frustum lesson written as a procedure. Two files agreeing
is not a measurement — both copies of that constant were wrong the same way for
three phases. A render agreeing with a derivation is.

---

## 5. The break, and the flood-through that does not exist

Retraction drops from 0.55 s to 0.30 s, because the passage is the point — the
hole is open within nine frames at 30 fps. The crack network the panel already
has flares over the last 0.10 s before it goes, so the wall is seen to give. The
slab then comes apart into **four substantial chunks** laid out along its own
chord, each carrying the panel's own radial thickness, 60% of its depth and its
own material dimmed, thrown outward along the break normal with a deterministic
tumble and gone in 0.42 s. Sparks drop from eight to five and from 0.55 to 0.22
in size: secondary, as the brief asks. Nothing has a collider and nothing is
read back.

**The flood-through moment is not in this simulation, and the reason is
structural.** The brief calls it potentially the best moment in the video. The
detection is exact — a `panel_break` opens a slot and `shell_exit` events with
`route == "break"` on that slot are the balls going through it. It returns
nothing at 1.8 s on all three candidates, nothing at 3.0 s, one/none/none at
5.0 s, and two/none/two at 8.0 s. Every shell rotates at 0.27 to 0.77 rad/s, so a broken slot is not
a door, it is a gap sweeping past the population; ball-ball collisions are off
and nothing steers, so no mechanism brings a second ball to the same slot in the
same second. Measured first-use delays are 0.36 to 14.44 s, and the *second* use
where there is one is 3.45 to 12.42 s after the break.

The mechanism is kept and correct, and a test asserts it stays empty so a future
phase that slows the outer shells finds out. What the renderer responds to is
the weaker tier that does fire — a single ball through a fresh passage, twice
per run. On 1176 the second of the two is the shell-4 break at 23.27 s used at
23.63 s: **that candidate's winning escape**, through a wall its team broke.

---

## 6. Hook, winner, balls

The hook faded from 1.0 to 0.22 at 3.4 s and stayed there — a ghost of the
question over the whole race. It is now solid for 1.85 s, gone over 0.55 s, and
the label is *hidden* rather than made transparent, so nothing survives a grade
or a thumbnail. No legend: at frame zero there are two balls, 65.5 px across,
one of each colour, under the words.

The winner banner picks whichever end of the frame the escaping ball is not at.

**The first version tested the escape instant and got the wrong answer, and the
rendered contact sheet is what caught it.** The banner comes up at the escape
and stays through the 0.55 s release beat, during which the escapee keeps flying
— it is the one ball with a canonical flight worth continuing, because there is
nothing outside the arena for it to hit. On 1176 the escape is 93 px clear of
the lower band at y = 1317.9 px and 0.55 s later the ball is at 1418.7 px,
inside it. `clear_of_ball` reported `True` for a frame with the caption under
the ball.

Placement is now decided from the escapee's whole swept extent over the release,
against both candidate bands, lower preferred. 17964 and 3762 keep the lower
band; **1176 moves to the top**, and it has to — its swept extent is 1300.9 to
1435.7 px. 17964's swept extent is 409.0 to 572.3 px, which is inside the *top*
band, so neither end is universally safe and the choice has to be made per
candidate.

Trails shorten from 0.16 s to 0.115 s and narrow, and the halo drops from 2.10
to 1.90. The trail is a world-unit length, so raising the frame fraction made
every streak 30% longer on screen without a constant changing; at eighteen balls
that is the spaghetti the brief warns about. Phase 4A's streak was 30.2 px at
its final framing against a 26.0 px drawn ball — the streak was the bigger
mark. 4B's is 28.3 px against a 33.9 px ball, so the ball is.

Ball counts, speeds, spawn timings and collision handling are untouched.

---

## 7. Occupancy

Analytic (material and balls as closed forms, clipped to the frame) and
measured (pixels above a luminance floor) are computed independently, and
neither is quoted alone.

**The two do not agree on a number and they are not supposed to.** Across the
eleven stills of 17964 the model sits *between* two pixel thresholds at ten of
them: everything brighter than the background (>0.14 luminance) runs 0.09 to
0.33 above the model because it counts the floor glow and the bloom, and
brightly lit material only (>0.30) runs 0.01 to 0.23 below it because the
model counts a panel's whole analytic annulus including its dim flank.

What they do agree on is the *ordering*, which is the agreement worth having
here. Over the 55 pairs of the eleven moments, the model and the ">0.14" count
disagree about which of two frames is busier **once**; the model and the
">0.30" count disagree seven times — and **every one of those seven involves the
escape still or the winner still**, where the escape flare and the caption put
bright pixels on the frame that the model does not count at all, because they
are neither arena nor ball. So no single number is "the" occupancy and none is
quoted as one.
The table below is the model, because it is the one that can be computed for a
candidate nobody has rendered yet.

| seed | early ink | middle ink | late ink | arena footprint |
|---:|---:|---:|---:|---:|
| 17964 | 0.303 | 0.208 | 0.174 | 0.319 at every stage |
| 3762 | 0.376 | 0.217 | 0.163 | 0.319 |
| 1176 | 0.375 | 0.298 | 0.160 | 0.319 |

**The brief's target here is not met and the arithmetic says why.** "The late
section should NOT become more visually empty than the opening" cannot hold for
a circle in a 9:16 frame under this camera: the opening framing holds two shells
across the frame *and* crops three more off the top and bottom, while the final
one holds all five inside it. What 4B does is raise the floor. On the same
final-wall still of 17964, measured four ways:

| fraction | analytic late ink | measured ink (>0.14) | measured solid (>0.30) | tallest empty band |
|---:|---:|---:|---:|---:|
| 0.652 (4A framing) | 0.089 | 0.258 | 0.044 | 579 px |
| **0.850** | **0.174** | **0.363** | **0.075** | **531 px** |

As in section 1, the 0.652 row is the Phase 4A *framing* with everything else
4B, so it isolates the fraction. Phase 4A's own final frame, with its shallower
depth ramp and its 1.55 pillars, carried less than the top row shows.

Every measure agrees on the size of the win: the late frame carries between
41% and 96% more than Phase 4A's did, depending on what you count as ink. The
frontier's own footprint is constant at 31.9% of the frame by construction,
which is the part the camera controls.

The tallest band of frame with no ink at all falls from 579 px to 531 px. That
is the review's "too much empty dark space", down 8% — real, and smaller than
the wish.

This is the one item in the brief that the phase does not deliver as written,
and it is left visible rather than redefined. See the open questions.

---

## 8. Tests

`tests/test_multishell_visual.py` 171 passed, `tests/test_multishell_av.py`
165 passed. Eight Phase 4A camera tests encoded the rule the review overturned
and were rewritten to the 4B contract rather than deleted; each rewrite says in
its docstring what the old assertion was and why it no longer holds.

New, grouped by what they defend:

**The camera.** The grouping is forced and not chosen. Windows are disjoint and
strictly outward. Protection only ever pulls a move earlier. No ball is ever
outside the frame. The first clone and the payoff are never inside a camera
move. The camera is locked for the whole final-wall section. The stage plan is
the one the scene draws. A reframe stays inside the stated velocity ceiling —
and is *faster* than the ball, so a return to one move per shell fails it too.

**The wall and the damage.** The depth ramp is re-derived from the frustum
rather than compared with a constant. A crack never leaves its panel at any
tilt it can take. The scene never scales an oriented basis. Damage is
impact-driven, deterministic, and builds with repetition. A panel draws at most
the wounds it has, worst first. The final wall shows the canonical wear the
five-state ledger hides, and that wear is a read of the `damage` stream rather
than a second opinion about it.

**The rest.** Fragments are deterministic and cannot reach the physics. The
passage response is derived, and the flood moment is asserted absent so a
candidate that finally has one is noticed. The hook leaves. The winner banner is
deterministic and clear of the ball across the whole release. The render config
digest covers every new dial. The scene defaults to the declared frame fraction
despite the laboratory dials existing. And 32 further shared constants and 2
ramps are mirrored between Python and GDScript, on top of the 50 Phase 4A
already mirrored.

The wider Category 3 regression — `test_multiplying_shell`,
`test_multiplying_shell_audio`, `test_multishell_av`, `test_multishell_visual`,
`test_shell_escape` and `test_tile_escape` — is **865 passed, 1 skipped, 0
failed**. `tools/two_team_phase4b_lab.py` had to be added to the named Category
3 exemption in `test_no_other_category_imports_category_three`, which is that
guard doing its job rather than a hole being widened.

---

## 9. Files

- `satisfying/multishell_visual.py` — the camera schedule and its guards; the
  damage-cluster, wear, fragment and passage derivations; and seven new reports
  (`containment`, `critical_visibility`, `occupancy`, `frame_size`, `wear`,
  `winner_banner_placement`, `camera_stages`).
- `satisfying/multishell_av.py` — `camera_report` reads stages rather than
  shells, and the velocity gate is stated rather than implied.
- `satisfying/multishell_visual_cli.py` — the audit diffs the scene's camera,
  wounds, wear and passages against the derivation.
- `godot/scripts/multishell_scene.gd` — the same schedule, the wound geometry,
  the wear read, the fragment sequence, the passage response, the overlay and
  the audit payload.
- `godot/scripts/multishell_render.gd` — two laboratory dials
  (`--frontier-width`, `--panel-depth`), neither of which changes a default.
- `tools/two_team_phase4b_lab.py` — the framing sweep and the pixel measurement.
- `tests/test_tile_escape.py` — the new lab tool joins the named Category 3
  import exemption.
- `docs/validation/category3_two_team_shell_race_v4b/` — evidence.

---

## 10. The three candidates, and what to look at

**17964 — chaos.** 18 balls, 9 cyan and 9 orange, 31 breaks, orange wins by an
opening at 25.78 s. The densest of the three and the one the framing sweep was
run on. Its final reframe lands 4.16 s before the payoff, the tightest of the
three, so it is the candidate that shows whether the locked final section is
long enough.

**3762 — the race.** 18 balls, multiple population and frontier lead changes,
cyan wins by an opening at 24.12 s. The candidate that eliminated 0.900: its
escape is at x = 995 px, and at 0.900 that is 43.5% under the action rail.

**1176 — destruction.** 12 balls, 20 breaks, and **orange wins by breaking
through the final wall** — the shell-4 panel breaks at 23.27 s and the winner
goes through the hole it made 0.36 s later. It is the only candidate in the set
whose climax is a break rather than an opening, it is the one that forced the
winner-banner fix, and it is where the new break sequence has to earn its place.

## 11. Review videos

540x960, 30 fps, H.264, AAC 192 kbit/s, against the unchanged open_quartal
masters at 48 kHz:

| seed | file | video | audio | drift | LUFS | true peak | clipped |
|---:|:--|---:|---:|---:|---:|---:|---:|
| 17964 | `output/category3_two_team_v4a/review/seed_17964_review_av.mp4` | 27.93 s | 27.93 s | +7.3 ms | −19.07 | −2.49 dBTP | 0 |
| 3762 | `output/category3_two_team_v4a/review/seed_3762_review_av.mp4` | 26.27 s | 26.27 s | −5.3 ms | −19.48 | −2.50 dBTP | 0 |
| 1176 | `output/category3_two_team_v4a/review/seed_1176_review_av.mp4` | 25.90 s | 25.92 s | −15.0 ms | −19.17 | −2.50 dBTP | 0 |

One frame at 30 fps is 33.3 ms, so every drift is inside the brief's tolerance
with the worst at 45% of a frame.

`sync_audit` re-validates the cue mapping itself rather than the container:
every canonical collision, clone, damage transition, break, shell crossing and
the winning escape maps to an audio cue, the audio is never retimed, video is
never early, and the maximum error is 0.9988, 0.9938 and 0.9969 frames — the
whole of it frame quantisation, which is bounded by one frame by construction.
Mean error 0.47 to 0.50 frames. `pass: true` on all three, recorded in
`av_sync.json`. `output/` is not tracked by git; the numbers
are in `docs/validation/category3_two_team_shell_race_v4b/mux_review.json` and
the frames a reviewer needs are in the contact sheets.

The stills and both sets of contact sheets are rendered at the **full
1080x1920**, which is what composition has to be judged at; the clips are
540x960 because they are for watching the motion, not for reading a frame.

**No production master.** The 1080x1920 60 fps clip profile was not run and no
upload candidate exists, as the brief requires.

Evidence, all under `docs/validation/category3_two_team_shell_race_v4b/`:

- `contact_sheets/seed_{17964,3762,1176}_sheet.png` — the eleven views per
  candidate, at render resolution.
- `framing/` — the four-way framing comparison, one sheet per view, plus
  `framing_sweep.json` with the per-frame pixel measurements.
- `phase4b_measurements.json` — every report for all three candidates, plus the
  twelve-row framing decision table.
- `render_audit.json` — the scene's own output diffed against the derivation.
- `occupancy_crosscheck.json` — measured pixels against the model, both
  thresholds.
- `mux_review.json` — the A/V join.
- `av_sync.json` — the cue-by-cue sync audit.

## 12. Open questions for the human review

1. **The final-wall gate's "accumulated damage", after the wear fix.** 3762's
   barrier now shows 19 scuffed panels of 66 where it showed none, and 17964's
   shows 10 of 66. That is wear, not cracking — the wall genuinely does not
   crack in these runs, because the brief froze the threshold. Does the frame
   now read as "this wall is being worn down", or does the gate need a
   candidate whose final wall actually breaks (which is 1176, and only in one
   place)?
2. **Late occupancy.** The brief asks that the late section not be emptier than
   the opening. It is — 0.174 against 0.303 on 17964 — and section 7 explains
   why that cannot be fixed by a camera that has to show the whole arena at the
   escape. The three levers that would fix it all cost something the brief
   forbids: a frame fraction above 0.900 (loses the payoff on 3762), an arena
   that is cropped rather than fitted at the final stage (the escape can be
   anywhere on the circle), or fewer/smaller shells (a simulation change). Is
   the current trade acceptable, or is one of those three worth reopening?
3. **The flood-through moment does not exist and cannot with these shells.**
   Rotation is what prevents it. Slowing the outer shells would be a physics
   change and is out of scope here; the mechanism is implemented and tested to
   be empty. Worth a future phase?
4. **Inner-shell damage at the final framing.** A shell-0 panel is 15 px by
   7 px there, so its wound is a few pixels whatever it is made of. The final
   wall's damage reads; the inner shells' reads as texture. Acceptable?
5. **Two frontier crossings on 17964 sit partly under the action rail**, one of
   them fully. 0.800 does not avoid the problem — it has one of its own — and
   costs 6% of every size. The hard classes are clear on all three candidates
   at 0.850, and on 17964 two of 78 crossings is 2.6%.
6. **The camera's screen velocity is 1.61x the ball's** where Phase 4A held it
   below 1.0. That is the arithmetic price of two transitions instead of four,
   and 0.45 s is already the slowest the brief allows. Does it read as a zoom
   the viewer notices?
7. **The static tail is 4.16, 4.98 and 5.21 s against the brief's 6-10 s.**
   The brief hedges this with "when candidate timing permits", and the timing
   does not permit: the final wall becomes the race frontier 4.47, 5.29 and
   5.52 s before the escape on these three candidates, and the camera locks
   0.31 s after that. The *whole* final-wall section is static apart from that
   0.31 s. Reaching 6-10 s would mean revealing the outermost shell before the
   race reaches it, which the same brief forbids — or picking candidates on a
   longer final section, which is a new seed search. Which?
