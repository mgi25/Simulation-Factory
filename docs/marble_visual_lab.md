# Marble Visual Lab — authored assets and the premium hero direction

**Branch** `marble-visual-lab`, based on `b649739` (the premium-toy style lock).
**Question asked** Can one static hero frame belong to the same visual family as
`docs/references/neon_marble_machine_concept.png`?
**Answer** Yes, and the thing that got it there was not colour.

This is an art lab. It contains no simulation, no course, no replay, no race
rules and no physics. Nothing in it can change what a race does — see
[Isolation](#isolation) for how that is guaranteed rather than asserted.

---

## 1. Why the previous prototypes failed

Five attempts came before this one — V0.3, V0.4, the neon proof, neon V1.1 and
the premium-toy style lock. All five were technically competent. All five were
rejected. The style-lock report blamed palette and lighting, measured its way
to a warmer rig, and still did not reach the concept. That diagnosis was
incomplete.

Putting the committed style-lock hero beside the reference makes the real
faults visible, and only one of them is about colour.

**It was the wrong shot.** The style-lock hero is a macro close-up of a single
bowl. The reference is a wide shot of a whole tower. At macro distance a module
has nothing around it to establish scale, so no amount of surface quality reads
as "premium product" — it reads as a render of a bowl. Framing was the largest
single fault and it is not a material problem.

**There was no structure.** Every earlier prototype rendered *track* and nothing
else: a bright object floating with a black surround. Measure the reference's
hero column and roughly two thirds of its lit area is dark scaffolding — masts,
belts, braces, deck plates, equipment — with the running surface as the
remaining third. That scaffolding is what gives the tower a silhouette, what
makes the track read as *mounted* rather than drawn, and what fills the space
between modules. Pull a camera back from four beautiful objects with nothing
between them and you reveal emptiness, not design.

**There was no medium scale.** The style-lock geometry had large forms (a bowl)
and small ones (bolts, trim) and almost nothing in between. Collars, housings,
brackets, guard frames, rail bodies and mechanical hubs are the layer the eye
resolves at hero distance, and it was missing.

**There was no place.** The reference sits on a cliff in haze with distant
lights. The style-lock sits on black. This matters optically as well as
narratively: a clearcoat lobe has nothing to reflect in a black room, so every
glossy highlight collapses to the direct lights alone and the machine flattens.

**The neon was missing.** The concept is called *Neon* Marble Machine. Its
defining feature is a lit edge running the length of every track, coloured by
zone. No earlier prototype had one.

Only the last item on that list is a palette question, and even it is really a
geometry question — a glow pass over a light surface is not a lit edge.

---

## 2. The authored-asset approach

The brief's central instruction was to stop forcing the hero through the
procedural course renderer. That renderer infers geometry from a 2-D course:
walls become boxes, runs become ribbons, and the ceiling those prototypes hit
is the ceiling of inferred geometry.

So this lab designs the machine instead. Blender is not installed on this
machine (`blender --version` finds nothing, and no install exists under
`Program Files` or Steam), so the authored assets are **code-authored Godot
meshes** rather than GLB imports. That turns out to be the better trade here
anyway: the meshes stay diffable, testable and parameterisable in the same
language as the scene, and the repo already carries a rounded-form mesh toolkit
(`godot/scripts/toy_geometry.gd`) built for exactly this.

### The pipeline

```
godot/assets/marble_machine/
    lab_palette.gd            the material language, quoted in hex
    lab_forms.gd              the medium-scale vocabulary
    start_platform/start_platform.gd
    hero_bowl/hero_bowl.gd
    s_curve/s_curve.gd
    collector/collector.gd
    support_tower/support_tower.gd
    backdrop/backdrop.gd

godot/scripts/lab_scene.gd    layout, rig, lenses, clock
godot/scripts/lab_render.gd   offline stills / clip renderer
godot/scenes/LabRender.tscn   the entry point
tools/visual_lab.py           the driver and the contact sheets
```

Each module is a `static func build(palette) -> Node3D` that returns a finished
subtree and knows nothing about the scene it lands in. The scene positions
them, hands the chutes their control points, and owns the rig. That is the
modularity the brief asked for in section 23, expressed the way a code-authored
project can actually hold it — a module can be lifted into another scene by
calling its `build`, and several already expose attachment points
(`HeroBowl.drain_local`, `StartPlatform.marble_slots`, `Collector.rim_local`).

Every builder is a pure function of its arguments. Nothing reads a clock or
randomises; where a scatter of parts is wanted the caller passes an index and
placement is arithmetic on it. Two renders of one scene produce byte-identical
meshes.

### Reproducing

```bash
export GODOT_BIN=".../Godot_v4.7.2-stable_win64_console.exe"
python tools/visual_lab.py hero        # the hero still
python tools/visual_lab.py variants    # tower / deck / spine
python tools/visual_lab.py lenses      # field-of-view and angle sweeps
python tools/visual_lab.py product     # one lens per module
python tools/visual_lab.py control     # the bloom-off frame
python tools/visual_lab.py compare     # concept | hero sheet
python tools/visual_lab.py motion      # the four-second clip
```

---

## 3. Layout, and the constraint that shaped it

Four modules on a vertical run of about eighteen units:

```
  16.4   START PLATFORM   eight bays, canopy, lit sign
           |  feed chute, swinging left
  11.3   HERO BOWL        dish, machined rim, aqua guard, cradle
           |  the S, swinging right
   2.5   COLLECTOR        stepped drum, five blades, gold tray
```

The obvious support layout — four columns on a rectangle with the modules
stacked inside — **cannot be built**. The bowl is 6.7 units across its acrylic
guard and the collector 5.9, so any column close enough to look like a tower
passes straight through a running surface. Every arrangement that avoids that
lands in the same place: a triangular frame standing *behind* the run, with
brackets reaching forward to take each module, and short post clusters filling
the gaps between modules where nothing else is in the way.

That is also what the reference has. Its alternative-angle panel shows the
lattice behind the track and never inside it.

The masts sit at `(±3.85, −0.70)` and `(0, −3.90)`; the nearest is 3.91 from
the machine's axis against a widest module radius of 3.36. The clearances are
constants in `support_tower.gd` (`GAP_LOWER`, `GAP_UPPER`) rather than numbers
in the scene, because they are a property of the frame.

The two chutes swing to opposite sides. That is composition, not physics: a
single S reads as a squiggle, and two curves mirroring each other around a
central bowl read as a machine with a plan.

---

## 4. Module design language

Three scales, deliberately weighted toward the middle one.

| Scale | Elements |
|---|---|
| **Large** | bowl, start platform, chutes, collector, masts, plinth |
| **Medium** | ring decks, collars, yokes, belts, guard frames, hub housings, cradle arms, equipment racks, blade assemblies |
| **Small** | neon ropes, bolt rings, fin tips, lamp chips, mast pips |

`lab_forms.gd` exists to hold the medium layer as shared vocabulary so four
modules speak the same language and a fifth can be added without inventing a
new one: `column`, `collar`, `brace`, `hoop`, `arc_hoop`, `plate`,
`smooth_path`, `offset_path`, `paddle`, `hub_housing`, `bowl_profile`,
`bolt_ring`, `equipment_rack`.

A few decisions worth not rediscovering:

**The bowl is one lathe.** Dish, rim, outer flank and underside come from a
single closed profile, so the rim highlight is continuous and the underside is
genuinely the same component seen from below. The style-lock bowl was a dish
with a separate ring balanced on it and the seam shows in every frame.

**A track is five layers in section**, not one surface: silver top lip, acrylic
side guard, silver channel, gold fascia, graphite keel. Each is a separate
sweep along the same spline, offset in the path's own frame so they cannot
drift apart. A ribbon is what you get when a track is one surface.

**Chutes are splines, not arc chains.** An arc chain has a curvature step at
every joint, and a glossy channel shows a curvature step as a kink in its
highlight — the clearest tell that a track was generated rather than moulded.

**Ring decks are what make it read as many levels.** Curved walkways wrapping
the back of the machine at 190°–350°, with rails, stanchions, a gold fascia and
an equipment rack each. Adding them was the single largest step change in the
whole lab. Without them a four-module machine is four objects with air between.

**The drain has to be a hole.** A dark throat, a gold collar, a lit inner edge.
It is the detail that says the marbles go somewhere.

---

## 5. Materials

`lab_palette.gd`. Three rules carried forward from the style lock, which were
correct — the failure was elsewhere.

* **Nothing painted is metallic.** Metallic trades diffuse for environment
  reflection and a dark backdrop has little to reflect. Moulded surfaces are
  `metallic 0.0` with gloss from `clearcoat`. Metal is spent only on hardware.
* **Every neutral is tinted.** Achromatic grey is what untextured default
  albedo looks like. Pearl runs warm, silver cool, graphite blue.
* **Warmth is structural.** Collars, fascias, hub housings and the whole finale
  zone are warm in every variant.

And one new rule: **colours are `Color("#RRGGBB")`, never floats.** GDScript
colour floats are sRGB, so `0.605` is not "sixty per cent bright" — it is
linear 0.31, under a grey card. Reading those floats as brightness is what
turned V1.1 grey. A hex string is the value that will be displayed.

| Role | Value |
|---|---|
| Track surface | `#D2D8DE` light silver |
| Module shells / bowl dish | `#E8E6E0` pearl |
| Brightest lips and caps | `#F7F4EE` |
| Structure | `#2A2E35` / `#191C22` / `#3A3F48` graphite |
| Acrylic guards | `#7FE0E8` aqua at α 0.125 |
| Gold hardware | `#E4AC3C` metal |
| Neon zones | cyan `#54E6F7`, violet `#9B6BFF`, orange `#F0813A`, gold `#F3CE86` |
| Racers | eight candy hues, separated by hue *and* value |

**The track is silver, not white** — taken straight off the reference's own
printed colour key ("Track Surface – Light Silver / Gray", "Supports – Dark
Graphite"). Running the chutes in pearl made them the brightest thing in frame
and destroyed the value separation between a chute and the bowl it feeds.

**Neon is geometry, not a post effect.** A rope of high-emission stock runs
down both flanks of every chute, outboard of the wall so it sits on the
silhouette, at an emission that crosses the bloom threshold on its own. A soft
strip tucked under a fascia cannot do that job. The accent is per-chute, so the
run reads as zones: cyan at the top, violet through the mixer, gold at the
finish.

---

## 6. Lighting

Product photography, not gameplay lighting.

| Light | Colour | Energy | Shadows |
|---|---|---|---|
| Key (directional) | `#FFF3E2` | 3.0 | yes, 4 splits |
| Rim (directional, behind) | `#8FD9FF` | 1.9 | no |
| Fill (directional, low front) | `#FFD2AC` | 0.40 | no |
| Start practical | cyan | 3.6 | no |
| Bowl practicals | violet ×2, cool top | 2.0 / 2.6 / 1.5 | no |
| Collector practicals | warm ×2 | 4.6 / 2.2 | no |
| Base wash | warm | 3.6 | no |

The style-lock rig failed the contrast test by being *only* soft: nothing was
hard enough to throw a readable shadow, so the machine had no darks. The key
here is a single directional with a tight shadow and the fill is deliberately
half a stop weaker than it wants to be.

Environment: ACES tonemap at exposure 1.0, a graded dark sky at 0.62 background
energy providing ambient and reflections, depth fog at 0.017 with aerial
perspective, SSAO, screen-space reflections, glow at 0.95 over a 0.92 threshold,
contrast 1.16 and saturation 1.14.

The sky matters more than its brightness suggests. It is what returns a faint
sheen along every rounded edge, and that sheen is most of the "photographed"
quality.

---

## 7. Camera

The brief ruled out the old 52° gameplay lens and asked for a sweep. Both
sweeps hold the machine at a **fixed vertical extent** and vary only the lens,
so the comparison is about compression rather than size — with distance fixed,
a longer lens is just a crop and the sweep says nothing.

`docs/validation/marble_visual_lab/lens_sweep_v1.png` — 30° / 35° / 40° / 45° / 50°.
`docs/validation/marble_visual_lab/angle_sweep_v1.png` — elevation 4° / 18° / 26°, azimuth 0° / 55°.

**Selected: fov 35°, elevation 18°, azimuth 33°, aim 9.6, extent 19.4.**

* Below 30° the tower flattens into an elevation drawing; above 45° the plinth's
  ellipse opens up and the base grows heavy.
* Elevation was the decisive axis, not field of view. At 4° the bowl is a white
  edge and the collector is a line. At 18° the camera sees *into* the bowl and
  down onto the collector's mechanism in the same frame, which is the whole
  reason the hero shot exists. At 26° the S-curve starts to overlap the
  collector it is delivering to.
* Azimuth 33° keeps the two chutes reading as separate curves; at 0° they
  superimpose and at 55° the feed chute crosses the bowl.

Four product lenses (`modules_v1.png`) share the identical rig and change only
the glass.

---

## 8. Hero frame iterations

Every step below is a change that was made because the previous frame was
looked at, not because a number moved.

| # | Change | What the frame said |
|---|---|---|
| 1 | Back-frame tower, four modules, pearl track, wrapping S | Collector buried under the S-curve's wrap; hard horizon line from the sky's ground colour; start platform illegible behind an oversized canopy; marbles too small |
| 2 | Both chutes rerouted to the front hemisphere, section tightened, sky horizon removed, marbles to r=0.30 | Modules legible and separated — but sparse between them, and no neon at all |
| 3 | Masts moved to `±3.85, −0.70` and thinned to 0.145; ring decks added; neon ropes added; glow raised | Density arrived. Read as clean chrome-and-glass on black |
| 4 | Backdrop energy to 0.95, zone practicals added | Colour zones landed, but the darks were gone and the collector blew out |
| 5 | Exposure pass: backdrop to 0.40, contrast 1.16, practicals halved, marble rim cut | Contrast restored, candy marbles restored |
| 6 | Track to silver per the reference's colour key; collector blades rebuilt as standing plates | Blades had been built *lying down* — `Forms.paddle` puts thickness on Y, so they were flat cards on the tray. Standing them up gave the module its silhouette |
| 7 | Elevation to 18° off the sweep; bowl dish stepped down a value, drain widened to 0.56; plinth to 3.95 | Bowl stopped clipping and its drain became visible |
| 8 | Backdrop settled at 0.62, marble count trimmed to ten | Final |

Two of those — the flat blades and the pearl track — were faults I could only
see by rendering a module in isolation and by re-reading the reference's own
printed colour key. Both are worth remembering as *classes* of mistake: a
helper's axis convention silently producing the wrong solid, and a design
answer already written on the reference that nobody had read.

---

## 9. Variants

`variants_v1.png`. Three materially different structures, not palette swaps —
they change support design, proportion, trim language and detail density.

* **`tower`** — three slim masts, a belt at every level, an X in every bay,
  post clusters in both gaps, three ring decks. **Selected.**
* **`deck`** — heavier masts carrying solid back-plates instead of diagonals.
  Calmer and more horizontal; reads as a cabinet, and the large flat panels
  kill the depth the lattice was providing.
* **`spine`** — one heavy back mast with cantilever yokes and two outriggers.
  The most open silhouette and the best joints, but too sparse: it loses the
  stacked-levels density that is the reference's signature, and its tie-rods
  read as loose wires at hero distance.

---

## 10. Isolation

Nothing in this branch modifies an existing tracked file. `git diff --stat
b649739` over the tracked tree is empty; every path is new:

```
docs/marble_visual_lab.md
docs/validation/marble_visual_lab/
godot/assets/marble_machine/
godot/scenes/LabRender.tscn
godot/scripts/lab_render.gd
godot/scripts/lab_scene.gd
tools/visual_lab.py
```

So `race_scene.gd`, `neon_scene.gd`, `toy_scene.gd`, `replay_viewer.gd`,
`offline_render.gd`, `render_replay.py`, `verify_race_render.py` and every
production tool are byte-identical to the base commit. The battle path, the
V0.4 production path and both retained art styles cannot have changed, and that
is a structural guarantee rather than a claim from a test run.

`lab_render.gd` is a sibling of `offline_render.gd` rather than an edit to it.
The lab needs a renderer that can point a camera at a scene with no simulation
behind it, and forcing that through a replay-shaped interface would have meant
inventing a fake replay to satisfy a contract the art question does not have.
What it keeps is the part that matters: an offscreen `SubViewport` at true
output resolution, a fixed warm-up count, and a clock that is the output frame
index rather than wall time.

**Test suite:** 1138 passed, 1 failed. The failure is
`test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised`,
which depends on `output/neon_v11/neon_7.json` — a gitignored render artifact
that does not exist in a fresh worktree, so `neon_proof.main()` reports the
missing replay before it ever reaches the Godot lookup the test is asserting
on. The same test passes in the `race-v1` worktree where that artifact exists.
It is a pre-existing artifact dependency in an existing test, not a regression.

No tests were added for art constants. There is nothing here a test can assert
that a person looking at the frame cannot assert better.

---

## 11. Performance

RTX 3050 Laptop, forward+, 1080×1920, MSAA 2×.

| | |
|---|---|
| Hero still | 0.6 s for the frame; ~2.4 s per Godot invocation including engine start |
| Four product stills | 3.4 s total |
| Motion clip | 240 frames in 66.4 s — 277 ms/frame, ≈3.6 fps |
| Clip size | 5.9 MiB, H.264 CRF 17 |

The clip renders offline at 3.6 fps and plays at 60. Nothing here is written
for real-time and the brief said visual quality wins; the costs are SSAO, SSR
and a 4-split shadow map on a scene of a few hundred small meshes. If this
direction ever has to run interactively, SSR is the first thing to drop and the
ring decks' stanchions are the first thing to instance.

---

## 12. Limitations, honestly

* **The environment is the largest remaining gap.** The reference sits in a
  *place* — a cliff, trees, haze, distant warm lights. This lab has three
  layers of dark slabs and a fog curve. It reads as a machine in a dark room
  rather than a machine on a mountain, and closing that gap properly is a
  set-dressing job, not a machine job.
* **The run is short.** Four modules against the concept's seven. There is
  visibly less track per frame than the reference has, and some of the
  reference's density comes simply from having more of it.
* **The frame is cool-dominant.** The gold finale anchors the bottom third but
  the middle is cyan, violet and silver. The concept's orange "choice zone"
  has no equivalent here because the split-choice module was out of scope.
* **The start platform is the weakest module.** Its canopy and sign read, but
  from the hero angle the bays are half-occluded by the feed chute's first
  metre, and the module contributes less silhouette than the other three.
* **Nothing here is physical.** Marble placement is composition. Chute gradients
  are drawn to look right, not to conserve anything. Several of these shapes —
  a true bowl, a drain as a hole, banked curves, drops between elevation levels
  — are things the current 2-D solver does not model at all. That is a question
  for the PyBullet phase and this lab deliberately does not answer it.
* **The acrylic is alpha-blended, not refractive.** It reads as cast acrylic at
  hero distance and would not survive a macro lens.

---

## 13. What should be reusable

Ranked by how confident I am it survives contact with the real machine.

1. **`lab_palette.gd`** — the material language. Zone accents, the non-metallic
   rule, the hex convention. Should be adopted wholesale.
2. **`lab_forms.gd`** — the medium-scale vocabulary. Independent of this
   layout entirely.
3. **The five-layer track section** in `s_curve.gd`. Any authored or
   generated chute should be built this way.
4. **The ring deck.** The highest value-per-triangle element in the lab.
5. **The back-frame constraint.** Any future layout has to satisfy it or its
   supports will pass through its running surfaces.
6. **The lens** — 35°/18°/33° at a fixed vertical extent, and the sweep tooling
   that chose it.
7. **`lab_render.gd`** — a scene-only offline renderer is useful for any future
   art question.

What should **not** be generalised yet: the module dimensions, the chute
control points and the light energies. Those were tuned by eye against one
composition at one aspect ratio, and the brief is right that deciding which of
them can safely vary is a later question.
