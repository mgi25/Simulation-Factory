# Premium toy marble machine — visual style lock

V1 asked whether a paused frame reads as three-dimensional. It did. V1.1 asked
whether it reads as *premium*, and the honest answer — once the frames were
measured rather than admired — is that it reads as a dark industrial factory.

This revision does not extend V1.1. It is a third scene beside it, playing the
same replay through the same contract, and it answers one question only:

> Can Simulation Factory look like a premium, colourful, tactile 3D toy marble
> machine, comparable in visual appeal to the approved concept reference?

Nothing about the race changed to find out. The simulation, the course, the
replay format, the two-dimensional physics and the winner are untouched, and
none of the new code runs any of them.

Deliverables:

| What | Where |
| --- | --- |
| Hero still | `docs/validation/toy_style_lock/hero.png` |
| Side-by-side | `docs/validation/toy_style_lock/comparison.png` |
| Three hero shots | `docs/validation/toy_style_lock/shot_{a,b,c}.png` |
| Palette variants | `docs/validation/toy_style_lock/variants.png` |
| No-bloom version | `docs/validation/toy_style_lock/hero_no_glow.png` |
| Phone-scale set | `docs/validation/toy_style_lock/phone/` |
| Motion proof | `output/toy_style_lock/toy_machine_visual_lock.mp4` |

---

## How to run

```bash
# everything: replay, variants, shots, hero, no-glow, phone, sequence, video, sheet
python tools/toy_proof.py --seed 7 --all

# or one step at a time
python tools/toy_proof.py --seed 7 --replay
python tools/toy_proof.py --seed 7 --variants        # the three palettes
python tools/toy_proof.py --seed 7 --shots --hero    # the three lenses
python tools/toy_proof.py --seed 7 --noglow --phone  # the two mandatory checks
python tools/toy_proof.py --seed 7 --frames --video --comparison
```

The neon proof is untouched and still runs:

```bash
python tools/neon_proof.py --seed 7 --all
```

Godot is found the way the rest of the project finds it: `--godot`, then
`$GODOT_BIN`, then the PATH.

---

## The measurement this revision is built on

Every claim below is a measured pixel statistic, taken with one script over
the committed V1.1 heroes and the new ones, using identical definitions. The
concept reference's own figures are in the third column.

| | V1.1 (mean of 3 heroes) | New toy style (mean of 3) | Concept reference |
| --- | --- | --- | --- |
| mean luma | 0.295 | **0.514** | 0.387 subject / 0.145 environment |
| pixels below L 0.15 | 52.8% | **6.8%** | 27.4% |
| warm pixels (R > B+15) | 1.0% | **33.1%** | 18.8% |
| achromatic share of lit pixels | 46.3% | **33.3%** | 14.3% |
| single most common colour | 16.2% | **8.6%** | 2.65% |
| clipped (L > 0.95) | 0.20% | 0.05% | 2.6% |

Per-frame figures are in the table at the end.

---

## V1.1's problems, named

### Gray dominance

Not a figure of speech. **46% of every lit pixel in a V1.1 hero is
achromatic** — channel spread of 10/255 or less — against 14% in the concept.
Sampled deck values come back `#A0A0A0`, `#989898`, `#686868`: not silver,
*untinted default albedo*. `#A0A0A0` alone covers 3.5% of the bowl hero.

The root cause is in `neon_materials.gd`. Its `TRACK_TOP` is
`Color(0.605, 0.592, 0.566)` — and those floats are **sRGB**, so the surface
renders as `#9A9790` with a linear reflectance of 0.310. That is four fifths
of a stop above an 18% grey card. The track was a grey card.

### Darkness

The bridge hero is **76.3% below L 0.15** and 69.9% below 0.10; its top 400
rows are 98.5% below 0.15. The blackness is also *flat*: one quantised colour
covers 21.3% of that frame and the top two cover 41.2%, against a 2.65%
maximum for any single colour in the concept.

Two numbers explain it. `ambient_light_energy` is 0.70 but the sky it samples
averages linear 0.017, so ambient irradiance is about 0.012 against a key of
1.56 — a **key-to-fill ratio of 1:131**. And `fog_light_color` is `#0C121D`,
so everything past 34 units fades *towards black* rather than towards haze.

Metallic compounds both. Track at 0.28, structure at 0.55, rail at 0.88, bowl
shell at 0.82 — metallic substitutes environment reflection for diffuse, and
the environment is a black room. Every one of those surfaces is a mirror of
nothing.

### Cold palette

Of all chromatic pixels, **92–95% fall in the 180–240° cyan/blue band and
1–4% in the warm band.** Frame-wide, warm pixels are 0.8–1.3% against the
concept's 18.8%. Every warm pixel in a V1.1 hero is a marble: background
regions return **exactly 0.0% warm**. There is not one warm structural
surface, warm bounce or warm practical in the machine.

The rig says why. Weighting each light by energy, the total is
`(2.000, 2.382, 3.021)` — **B/R 1.51, with 33% of luminous energy off-key and
100% of that blue**. There is no warm fill anywhere in the file.

### Industrial forms and repeated geometry

The edge histogram does *not* support a global boxiness claim — V1.1 is 46%
axis-aligned against the concept's own 42%. The failure is narrower and worse:

* The chute is a straight extrusion with a square lip. Sampled across a
  12-pixel stripe, luma varies by **≤3/255** — the signature of a flat facet
  with no curvature shading, no fillet, no specular roll-off.
* Stripe pitch on the chutes is a median **9.0 px**, one every 1.7% of frame
  width, four channels carrying the identical pattern. At the 0.559× phone
  downscale that aliases into a 5-pixel moiré, so the corrugation gets
  **sharper** as the image gets smaller. Local-detail retention at phone
  scale: marbles 82–87%, chutes 101–121%. The toy softens and the factory
  sharpens — exactly backwards.

### Small marble importance

Median marble diameter is **23 px at 540 wide** and all sixteen together cover
**0.55–0.93% of frame**, against **5.86%** in the concept's hero column — and
the concept's start tile reaches 5.10% with only nine balls. A marble occupies
24% of its channel's width where the concept's nearly fills it. The hero of a
marble run was a garnish.

---

## The new style, and what each change is answering

### Palette: every neutral is tinted, and warmth is structural

`toy_materials.gd` carries three variants; every colour is quoted with the hex
it actually displays as, so the sRGB mistake cannot be made twice. Nothing in
it is achromatic.

Warmth is put where it cannot be removed by a change of accent: a warm
directional fill, warm hardware on every module, warm underlighting, a warm
practical under the bowl, and a warm zone light over the track. The result is
**33.1% warm pixels against V1.1's 1.0%**.

### Materials: nothing painted is metallic

Every moulded surface is `metallic = 0.0` and buys its gloss from `clearcoat`
at 0.86 — a dielectric second lobe that costs nothing in albedo, which is
physically what a moulded part under lacquer is. V1.1 used clearcoat on
exactly two materials. Metal is now spent only where it is meant to read as
metal: warm hardware, at 0.82 metallic and 0.26 roughness.

### Rounding: three exact builders, no deformed primitives

`toy_geometry.gd` is the file the mandatory rounding rule cashes out in. Godot
ships a box, a sphere, a cylinder and a torus, none of which has a rounded
edge, so:

* `rounded_box` — six flat faces, twelve quarter-cylinder edge fillets, eight
  spherical corner octants. Exact, not a deformed sphere, because the flat
  faces are where a moulded surface shows its shading gradient.
* `lathe` / `rounded_disc` — surfaces of revolution with caller-supplied
  profile normals, so the caller decides which joints are creases and which
  are fillets. Every part of the bowl is one profile.
* `sweep_profiles` — a cross-section carried along a path with its own
  section at every sample, which is how a track widens where the course opens.
* `channel_section` / `beam_section` — the running channel and the beam under
  it, both radiused.

Every quad goes through `quad_auto`, which measures the cross product against
the normal it was given and reverses the corner order when they disagree. That
costs one cross product per quad at build time and removes an entire class of
inside-out-surface bug across eight sign combinations.

Verified: `rounded_box(2.0, 0.5, 3.0)` returns an AABB of exactly
`(2.0, 0.5, 3.0)`; `rounded_disc(1.0, 0.3)` returns `(2.0, 0.3, 2.0)`.

### Construction: light lip, warm fascia, dark keel

The single most useful thing the concept gave up under measurement is how its
beams are built. A track beam is ~15 px deep on a ~40 px deck, split as a
**~5 px silver top lip over a ~10 px brass fascia** — and that fascia is where
a third of the image's warm coverage lives. Under both is structure at value
0.15 against a track at 0.75, a **1:5 ratio**, which is *why* a light track
reads as a light track.

So every channel here is three parts: a pearl moulded channel, a brass fascia
beam under its lip, and a graphite keel under that. The first pass of this
scene was cream from running surface to underside and came out monochrome; the
frame it produced had no anchor and the components had no thickness.

### One channel per section, not four

V1.1 splits each section into every separately-walled run and sweeps a beam
through each — which is what produces the four striped decks that alias at
phone scale. This scene takes the **envelope** instead: at each sampled
height, the union of everything walled on both sides, as one moulded channel,
with a raised moulded island where the course's own wedge splits the feed.

It is guaranteed to have floor under every racer for the same reason V1.1's
builder is — the width is the course's own clear span, not a number chosen by
eye — and it gives each section one continuous silhouette rather than a
repeated one.

### Lighting: a lit dome, a warm fill, a cool rim

* Ambient raised from a 1:131 key-to-fill ratio to roughly **1:5**, and the
  sky is a real softbox rather than a near-black probe.
* The dome lights and reflects at full strength but is *drawn* at
  `background_energy_multiplier = 0.34`, so the environment sits well below
  the subject the way the concept's does. Lighting the room with the same dome
  that lights the machine gave both the same value — a machine with nothing
  behind it.
* Key at **−56°, 24°**, which is the concept's own key angle, measured off the
  specular blob on its legend racers.
* The fill is **warm** (`#FFCF9C`) and the rim is **cool**, so the two off-key
  sources pull against each other instead of together. V1.1's were both blue.
* Fog now hazes towards the backdrop colour instead of towards black.
* **AgX** rather than ACES. ACES rolls a saturated blue towards cyan and a
  saturated red towards orange — tolerable when the only saturated objects are
  small, fatal when they are the subject.

### Zone colour is light, not paint

The concept's governing law, and it took measuring to see: **its track albedo
never changes.** The same surface is sampled at V 0.73–0.81 in all seven zones
while its red-over-blue ratio climbs monotonically from 0.93 at the start to
1.27 at the finish. Value held, hue ramped — by the light. So zone colour here
is two large soft practicals plus a floor bounce, not a tinted material per
section, and it survives a change of palette.

### Marbles: the multiplier does not work, and the replay says why

The obvious lever for "bigger marbles" is a multiplier on the drawn radius.
It fails, measurably. Across all 616 frames of the reference run the closest
pair of racers is **57–60 course pixels apart against a simulation diameter of
60** — the field is in contact in **100% of frames**, because a marble run is
a pile-up. Any multiplier above 1.0 therefore draws intersecting spheres in
every frame; at the 1.70 this scene was first built with, two touching marbles
overlapped by 42 px of a 102 px diameter and the bowl rendered as one fused
blob.

`MARBLE_SCALE` is 1.00. Apparent size is bought the other way the brief
offers: **eight racers instead of sixteen, and hero lenses that fill the frame
with the module they are about.** That is the honest way round — it makes the
marbles bigger *in the picture* without drawing a field the simulation did not
produce.

Material is candy: metallic 0, roughness 0.12, clearcoat 1.0 at 0.02
roughness, a small untinted rim, **no emission** — because a glowing sphere
has no terminator, and the terminator is what makes a sphere a sphere.

No number plates. At phone scale a V1.1 racer number is ~5 px of cap height
against a ~10 px legibility floor, so the plate cost a silhouette and bought
nothing. The brief also asks for a plain marble to be made beautiful first.

### Composition and cameras

Three fixed product lenses rather than moments of a follow-cam, because the
question is whether the *object* is desirable:

| Shot | Lens | What it has to show |
| --- | --- | --- |
| A establishing | 46° fov, 34° elevation, 158° azimuth, 16 u | feeder, bowl, track, machine height |
| B bowl hero | 36° fov, 30° elevation, 56° azimuth, 19 u | acrylic, bowl depth, marbles, cradle |
| C track hero | 42° fov, 23° elevation, −46° azimuth, 11 u | the curve, the underside, the supports |

Shot A is taken from *below* the machine looking back up it. Every
downstream-facing lens framed the bowl and nothing else, because the machine
descends nine units over thirty-four and a camera above the start is looking
at the back of its own subject. From past the track, the three modules stack
and the nine units of drop become nine units of frame height.

`--toy-cam=aim,lift,distance,elevation,azimuth,fov` renders any framing from
one build, which is how these were chosen — by looking at six side by side,
three times over, not by argument.

### Background

A product sweep, two ranks of rounded pylons, five very large soft light
panels and a floor. The first pass built a hall — close ranks, a panel wall,
arches over the machine — and every element became a dark bar crossing the
subject. Pushed out and reduced, the single most common colour falls from
16.2% of frame to 8.6%.

---

## The three variants, and why A

`docs/validation/toy_style_lock/variants.png` — identical geometry, identical
camera, identical replay, identical moment. Only the palette differs, because
that is the only thing the comparison is about.

* **A — Pearl + Aqua** — pearl-ivory channels, aqua acrylic, gold hardware,
  graphite structure, cool slate room.
* **B — Warm Toy** — cream channels, lighter acrylic, the same hardware.
* **C — Futuristic Candy** — silver-white channels, the most saturated glass.

**A is selected**, judged at 1080×1920 and again at the 302×538 a Short is
actually watched at:

* At phone scale **B goes beige**, and the yellow and orange marbles lose
  separation against it. A holds a clean warm white that the eight marble hues
  all read against.
* A's aqua acrylic is the most visible of the three at phone size, which is
  the brief's specific requirement for it, while C's cooler whites make the
  gold hardware the only warm thing in frame.
* A is warm enough to escape C's clinical, appliance-like register without
  B's muddiness.

This was not unanimous. Four independent reviews of the three palettes scored
them 27 / 24 / 27 in aggregate: one preferred B's register outright ("cream
and brass reads as a toy before it reads as a render"), two preferred C on
reference fidelity and phone-scale risk, one preferred A. A is chosen on the
rendered frames rather than on the specifications, and the disagreement is
recorded because the difference between the three is genuinely small once the
room and the hardware are shared.

---

## Bloom is not load-bearing

`hero_no_glow.png` is the same frame with `--toy-no-glow`, out of one build of
one scene from one replay. The two are near-indistinguishable: the glow
threshold (1.30) sits above every emissive material in the palette, so nothing
in the picture depends on the post-process. Clipping is **0.05%** of frame.

---

## What is still short of the reference

Stated plainly, because the brief's standard is the image and not the effort.

1. **The machine is still substantially neutral.** 33.3% of lit pixels are
   achromatic against the concept's 14.3%. The colour that exists is the eight
   marbles, the aqua acrylic, the gold hardware and thin accent lines; the
   concept's machine wears large coloured lights and the running surfaces pick
   them up. Saturated colour is 6.5–12.3% by frame against the brief's own
   10–15% target for zone colour — inside the band on two shots, under it on
   the hero.
2. **The frame is now brighter than the thing it is imitating.** 6.8% of
   pixels below L 0.15 against the concept's 27.4%. That is a deliberate
   over-correction of V1.1's 52.8%, but it costs deep shadow, and deep shadow
   is part of why the concept looks expensive. A future pass should give value
   back to the environment without giving it back to the machine.
3. **The bowl basin is the largest single surface in every hero frame** and
   the two concentric bands added to it are not enough to make its middle
   interesting.
4. **The start platform is barely in the hero.** The chosen lens frames feeder,
   bowl and track; the display platform and its START sign only read in the
   motion proof's opening seconds.
5. **The mechanical element is small in every frame.** It reads as a detail on
   the bowl rim rather than as a module.
6. **One module, not seven.** The concept is a seven-stage tower whose
   silhouette is an hourglass with two discs bookending it. This is a feeder,
   a bowl, a curve and one machine part. The comparison sheet is honest about
   that and it is the correct scope for a style lock.

---

## What the physics phase will need

Documented only. No physics was written, changed, or planned into the code.

The visual geometry now asserts things the two-dimensional solver does not
model, and these are what the next phase has to reconcile:

* **A true bowl.** The renderer derives world height radially from
  `bowl_surface_y(rho)`; the simulation runs flat x/y with gravity along +y.
  A marble that looks like it is riding the inner wall is, underneath,
  sliding down a plane. Orbiting, banking and the loss of speed to a climb
  are all absent.
* **Banked curves.** The swept channel has real walls with a radiused
  transition; the simulation has vertical wall boxes and no bank angle.
* **Drops between elevation levels.** `deck_height` spans nine world units
  across five sections, and the transitions are eased for the eye. The solver
  sees one plane.
* **The drain as a hole.** Racers pass through the drain at the bowl's centre
  in the picture; in the simulation they pass a y-plane.
* **Curved track length.** The drawn S-curve is longer than its projection,
  so a marble's drawn speed and its simulated speed disagree around a bend.

None of that is a defect in this prototype. It is the list the physics phase
starts from, and it is why the two problems were kept apart.

---

## Testing

Full suite: **1139 passed**, up from a 1122-passing baseline — seventeen new
tests in `tests/test_toy_proof.py`. No existing test was changed.

Verified unaffected:

* **The V0.4 production race path**, checked the strongest way the project
  has: a `machine`-course replay rendered through `tools/render_replay.py` on
  the verification camera and measured by `tools/verify_race_render.py` —
  *168 racer positions located, 0 missing, mean error 1.21 px, worst 11.27 px
  against a 16 px tolerance.*
* **The neon V1.1 proof**, which still renders through Godot from
  `tools/neon_proof.py`, and whose committed stills are byte-identical after
  this branch's changes.
* **Battle mode**, rendered from a `batch_audit10` replay.
* `rendering/deck_geometry.py` and its agreement test with `neon_scene.gd`,
  which this scene deliberately does not touch.

The new tests assert the things that would silently break a render — the
scene/tool agreement on the shipped variant and hero shot, the replay's
determinism, the marble-contact measurement that fixes `MARBLE_SCALE` at 1.0,
and that the toy path selects the toy scene. They do not assert artistic
constants.

## Render performance

RTX 3050 Laptop, Godot 4.7.2, Forward+, 1080×1920:

| Pass | Cost |
| --- | --- |
| stills-only run (any number of moments) | 0.5–1.3 s |
| full 616-frame sequence | 176 s — 3.5 fps, **285 ms/frame** |
| ffmpeg encode of the 300-frame clip | ~4 s, 3.4 MiB |
| `--all` end to end | 3 min 31 s |

The sequence is 80× slower per frame than the neon scene's 1 ms because the
machine is now built from swept and lathed meshes with per-vertex normals
rather than from boxes, and because ambient, reflections and SSAO all do real
work against a lit dome. It is still comfortably faster than real time to
render, and the stills path — which is what art iteration uses — is
effectively instant.

## Per-frame measurements

| Frame | mean L | < L0.15 | warm | achromatic of lit | saturated | top colour |
| --- | --- | --- | --- | --- | --- | --- |
| V1.1 bowl hero | 0.426 | 27.3% | 1.3% | 47.1% | 15.2% | 10.9% |
| V1.1 start hero | 0.274 | 54.7% | 0.8% | 42.0% | 10.5% | 16.3% |
| V1.1 bridge hero | 0.184 | 76.3% | 0.8% | 49.9% | 6.0% | 21.3% |
| Toy hero (shot A) | 0.539 | 4.1% | 33.5% | 31.7% | 6.5% | 8.9% |
| Toy bowl hero (B) | 0.554 | 6.7% | 24.0% | 42.7% | 11.2% | 8.7% |
| Toy track hero (C) | 0.449 | 9.5% | 41.7% | 25.6% | 12.3% | 8.3% |

## Files

New:

* `godot/scripts/toy_geometry.gd` — rounded-form mesh primitives
* `godot/scripts/toy_materials.gd` — the palette, in three variants
* `godot/scripts/toy_scene.gd` — the scene
* `godot/scripts/toy_geometry_check.gd` — a headless AABB check for the above
* `tools/toy_proof.py` — the proof pipeline
* `tests/test_toy_proof.py`

Changed:

* `godot/scripts/replay_viewer.gd` — `--race-style=toy` routing, and the
  two style ternaries replaced by one lookup each so a fourth style is one
  entry rather than four edits.

Untouched: the simulation, the course, the exporter, the encoder, the neon
scene, the neon palette, the race scene and every production path.
