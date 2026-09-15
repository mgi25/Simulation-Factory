# V25.2 — the final world lookdev

**Status: built, measured, awaiting review. Not merged. Not integrated with V24.**

V25.2 is a lookdev pass over V25.1. The race is the same race: same seed, same
replay, same solved camera tracks, same edit, same cues, same 1340 frames, same
machine. The world is in the same places, at the same density, built from the
same two kits.

    --environment=aurora_valley_v252     the world, one lookdev delta
    --machine=v23b                       the machine, V23's, unchanged

Branched from `origin/v251-world-art-polish` (`4fc8d47`). V24 is untouched and
is not a base for anything here.

**V25.1 renders byte-identically from this branch.** Thirteen frames, two
tracks, md5 for md5, before and after every change in this pass — see §13.

---

## 1. The problem after V25.1

V25.1 was right about forms and its own record says what it cost. Its §12
measured the thing the review then complained about, and then — correctly —
refused to explain it away:

| | V25 B | V25.1 |
| --- | ---: | ---: |
| midground ridges, pixels under grey 12 | 22.6% | **42.2%** |
| midground ridges, median grey | 17.0 | **14.3** |

Every other depth band got lighter and more readable. The midground got darker
and higher in contrast, and V25.1 swept three lighting fixes against it and
falsified all three. Its conclusion was that *the tail is intrinsic to flat
shading*: each facet has one value, a histogram has low bars, and no lighting
dial removes them.

**That conclusion is right about lighting and is not the end of the argument.**
A pixel's value is albedo × the cosine of the angle between a normal and a
light, summed over lights. V25.1 swept the third term three times. The other
two were never touched:

1. **the normal**, which V25.1 fixes at one per face by construction, and
2. **the albedo**, which is one constant per material over a mass a hundred
   units tall.

So this pass is those two terms, plus one material response that is not a
light. Everything else follows from the room that buys.

The review's other four complaints are the brief's other four jobs and are
answered in §§3–7.

## 2. What is in this pass, and what a delta means

`tools/sloped_v252_profiles.py` writes `aurora_valley_v252`, which **extends
`aurora_valley_v251`** and carries deltas only.

That is a deliberate break from V25.1's own practice. V25.1 restated the whole
`world` section, because its brief made V25 B's density a *target* and a target
is something to state. This brief makes V25.1's layout a *lock*, and the way to
keep a lock is to inherit it: every ring, bearing, radius, count, site and kit
assignment in V25.2 is V25.1's because V25.2 never mentions it.
`test_the_profile_restates_no_layout` asserts exactly that, and §13 lists what
else is nailed down.

Three source files gained options; none gained a default.

| file | what was added | default |
| --- | --- | --- |
| `world_rock.gd` | `temper`, `crease`, `shade`, `jag`, `overhang`, `shoulder` | all off |
| `world_flora.gd` | `bough`, `ragged`, `aspect`, `stem_width`, one kind (`snag`) | all off; `snag` in no cluster |
| `environment_world.gd` | `patches.smooth`, `trees.roles`, a measured rejection reason | off; falls back to the kit |
| `lab_palette.gd` | `soft_light`, `edge_light`, `floor_lift`, `vertex_tint`, three surfaces | inert unless named |

## 3. Part A — the midground shading

### `temper`: crease-limited normal softening

Each corner of a quad is blended from its own face normal toward the average of
the faces meeting at that corner — **but only across edges shallower than
`crease`**, which is 42° everywhere in this profile.

Two properties make this the right instrument rather than "smooth the rock":

* **The geometry is untouched.** Not a vertex moves, not a triangle is added,
  the silhouette is identical. `_face` even winds each quad against the
  *untempered* face normal so a tempered quad winds exactly as it did in V25.1.
* **42° is one number that behaves differently per form.** The plan step on an
  11-facet mass is 33° and on a 7-facet needle is 51°. So the crowded facets of
  a wide cliff blend and the few facets of a spire do not, and a ledge step, a
  notch wall and a chorded flat's corner — the edges the kit's whole argument
  rests on — are all past the threshold and stay exactly as hard as they were.

Per band: walls 0.70, far ridges 0.66, near ridges 0.62, finish arc 0.58, merge
0.54, banks 0.52, obstacle wall 0.50, split 0.48, scarps 0.46, boulders 0.44,
gorge teeth 0.34, **spires 0.30**. Highest where the mosaic is worst and the
form is furthest; lowest on the needles, because a spire is a silhouette and
softening it spends the one thing it has.

### `shade`: a large-scale albedo gradient, baked to vertex colour

Two terms at the scale of the whole form, because the style lock bans
high-frequency surface variation: a lift toward the crown and a fall into the
foot, and a restrained warm or cool turn by aspect. Multiplied into the
material by `vertex_tint`, in linear space.

A facet is still one value. **The form is no longer one value**, which is the
difference between twelve dark polygons and one sculpted mass.

### `soft_light`: a shadow floor that is not a light

Godot's backlight adds `backlight × (1 − N·L)` per light: a term that is zero
on the faces the key already reaches and largest on the faces it misses
entirely — which is the exact shape of this problem.

A fifth directional light would have raised the lit faces too, given the faces
pointing at *it* a second key, and — being a light — been one profile mistake
away from the machine. This cannot be: it is a field on nine world materials
and the machine's materials are not in the table.

### The albedos come up, and the hue spreads out

V25's base darkened the kit's own values hard — `world_rock` to #0C1119, which
is L\* 6 — so the recession would survive and the machine would stay hero. At
L\* 6 a facet the key misses has nothing left to render. Each surface comes up
four to six L\*, keeping the six-L\* spacing between the depth pairs V25.1's §3
argues for.

And the hue spreads, which is the anti-monochrome move and costs nothing:

| band | V25 base | V25.2 | reads as |
| --- | --- | --- | --- |
| foreground `world_scarp` | #0F141D | **#1D2229** | near-neutral slate |
| midground `world_cliff_face` | #111826 | **#19202F** | blue |
| valley walls `world_wall_face` | #151E2E | **#1B2739** | bluest thing that is not sky |

V25's recession is carried by *value* alone — six surfaces, one hue — so a
world with five depth bands still reads as one colour. Aerial perspective is a
hue effect before it is a value effect: what is close is the local stone and
what is far is the colour of the air between.

### Result

Segmented off the marker render, pooled over the ten race moments:

| | V25.1 | V25.2 |
| --- | ---: | ---: |
| **midground ridges, pixels under grey 12** | 22.4% | **2.7%** |
| valley walls, pixels under grey 12 | 3.5% | **1.0%** |
| midground ridges, median local value spread | 4.0 | **4.1** |
| valley walls, median local value spread | 3.1 | **2.4** |

**The tail went and the modelling stayed.** The dark share of the midground
falls by a factor of eight; the *local* value spread — peak-to-trough inside a
41-pixel window, which is the mosaic measured as a number — does not move at
all on the ridges. That pair is the result this pass wanted and is worth more
than either number alone: a pass that had flattened the rock would have driven
both to zero, and a pass that had only raised a light would have moved neither.

`docs/validation/sloped_race_v1/v252_world/crop_midground.png` is the picture
of it: the same cliff, the same outline, the abrupt facet-to-facet steps
replaced by a surface that turns.

## 4. Part B — the hero rocks

Silhouette first. Three options, all of which move the *outline*, spent only on
the formations the race cameras stand closest to — and spent **unevenly**,
because every form getting one of each is a new repeated shape.

| option | what it is |
| --- | --- |
| `jag` | each crown-rim vertex gets its own height, so a flat top stops drawing a straight line across the sky and still reads as a top |
| `overhang` | a ledge that steps *outward*: the one silhouette event a taper cannot produce, and the only one that puts a face into shadow no fill reaches |
| `shoulder` | a secondary mass at 62–88% of the height, where `buttress` is one at 38–62%. A buttress broadens a foot; a shoulder breaks a skyline |

| formation | jag | overhang | shoulder | also |
| --- | ---: | :---: | :---: | --- |
| obstacle east wall | 0.13 | ✓ | ✓ | its own stone, 10 units taller, §6 |
| finish basin arc | 0.26 | ✓ | ✓ | re-solved against the lens, §7 |
| split gate | 0.14 | | ✓ | |
| merge narrows | 0.08 | ✓ | | |
| gorge teeth (start/mixer) | 0.09 | | | needles: silhouette is all they have |
| boulders (the closest rock to any lens) | 0.16 | | ✓ | |

The hero rock's measured local value spread falls 28.6 → 26.3, which is a small
number doing a small job: the crop is what the claim rests on.

`overhang` also forced one correction in the generator. `_scaled` now clamps
the per-facet radius **above** as well as below, because an overhang is a
negative shed and without the clamp a low-taper kind carrying one would grow
past its own foot — out through a keep-out that was sized against the foot, and
in breach of `form()`'s own promise that `base_radius` is the widest point.

## 5. Part C — controlled warmth

The brief's hierarchy, implemented in that order and nowhere else.

**Warmest: the finish.** `world_warm_rock` was #242130 in V25.1 and the first
version of this pass made it #2E2833. **Both have more blue than red**: "warm
rock" was a cool grey with a warm name, and the measure caught it before the
eye did — the finish's warm-pixel fraction came back *lower* than V25.1's. It
is now #3B3029, red leading blue by seventeen levels, plus 0.40 of warm in the
vertex gradient, plus one practical (§7).

**Second: machine-adjacent structure.** `world_concrete`, `world_deck` and
`world_deck_dark` take a quarter-stop of warmth and a lifted floor, so a bench
wall in shadow is a wall rather than a hole.

**Third, very subtle: selected rock faces.** `shade_warm` at 0.05–0.12 on the
near ridges, the scarps, the boulders and the obstacle wall — a turn on the
faces the fill rakes and nothing on the others.

**Almost none: the far mountains.** `shade_cool` only.

Four dials on the light rig, no new light, and the world's total moves under a
tenth of a stop:

| light | V25.1 | V25.2 | why |
| --- | ---: | ---: | --- |
| `WorldKey` | 1.58 | **1.52** | pays for the rest |
| `WorldWarm` | 1.05 | **1.20** | the same fill buys more against tempered normals: it lands as a gradient turning across a form instead of a second flat value |
| `WorldBounce` | 0.55 | **0.70** | V25.1 falsified this *before* the material floor existed. It now finishes the job instead of being the job |
| `WorldRim` | 0.66 | **0.50** | see below |

**`WorldRim` comes down, and that is the dial that moves the way nobody
expected.** V25.1 raised it from 0.55 to 0.66 with a good argument — "a rake has
edges to find now" — and against tempered normals that argument inverts. A rake
on a hard facet catches one edge; a rake on a tempered one catches a whole
turning surface, and `WorldRim` is #63BEE8. The first V25.2 render put a cyan
sheen across every upward plane of the finish rim, which is the
"monochromatic" complaint and the "prototype-like" one arriving together. 0.50
is under V25's own 0.55, and the edges still read because they are now the only
thing it catches.

## 6. Part E — the obstacle pocket

**The brief is right that the obstacle camera does not see mid-distance, and
the segmentation says how right.** At 10.2 s, by band:

| band | share of frame |
| --- | ---: |
| terrain (the near hillside) | **31.5%** |
| foreground rock | 6.9% |
| ravine floor | 3.2% |
| midground ridges | **1.8%** |
| valley walls | 0.9% |

The top eighth of that frame is foreground rock and everything from v = 0.25
down — five eighths of the picture, up to 100% of some rows — is the ground. A
landmark cannot carry this shot. **The ground has to.**

So the pocket is built out of what is there, and nothing is added:

1. **Two of the eleven material zones become the obstacle's own stone.** The
   zone at (−10, −4) is centred within a unit of the obstacle node and the one
   at (−9, 10) sits just up-course; repainted `world_pocket_floor` and
   `world_pocket_grit` — a slate pair, close to the hillside in value and off
   it in hue, one of them a stop rougher. No zone added, none moved, the first
   widened from 16 to 19 units.
2. **A warm/cool lighting pocket.** V25.1's obstacle practical sat nine units
   *under* the track, where what it lit was the underside of the deck. It moves
   above the pocket floor on the camera's own side and goes 0.9 → 1.35.
3. **The east wall becomes a canyon wall.** One unit in, ten units taller, its
   own stone (`world_pocket`), an overhang high on the mass and a shoulder
   above it.

### Two corrections the builder forced, and one bug it exposed

The first build asked the east wall in to 48 units and `environment_world`
rejected it: a landmark inside the 16-unit camera keep-out is skipped, so the
obstacle frame came back with *less* rock than V25.1 had. The second asked for
54 through `sloped_v251_profiles.near()` and was rejected at **8.4 units from
the camera path, which is not where 54 is** — `near()` converts an absolute
plan position into a terrain-relative offset, and a site that names a `node`
wants a plain node-relative offset, so it was being added to the anchor twice.

That is in the record because of what it cost to find: "inside 12.0 of the
racing line or 16.0 of the camera path" does not say which of the two, or
whether the fix is one unit or ten, and each guess is a fifteen-second render.
`environment_world._why` now reports **both measured distances** on every
landmark rejection, and the second bug fell out of the first render after it.

**And the world-cover number was wrong in the flattering direction.** The
obstacle's two ground zones were first painted with the obstacle's *rock* key,
which `sloped/v252_world.MARKED` puts in the midground band — so the measured
world cover at the obstacle went from 12.5% to **39.3%** with no object added
anywhere, and at the fork approach from 45.7% to 72.0%. A material may not
belong to two depth bands: the rock is one key and the ground is two others.
Corrected, the obstacle reads 12.5% → 13.0%.
`test_every_surface_the_profile_paints_is_in_exactly_one_band` is the assertion
that would have caught it, and now does.

## 7. Part F and G — the finish as a destination

### The finding this section is built on

V25.1's finish basin — five masses on an arc, the thing built to make the
finish a place — **is outside the finish lens.**

Projecting the arc through the camera's own solved transform at 21.4 s:

| arc mass | crown at screen u | crown at screen v |
| --- | ---: | ---: |
| 0 | 1.64 | 0.36 |
| 1 | 1.04 | −0.07 |
| 2 | **0.29** | **−0.34** |
| 3 | −0.41 | 0.01 |
| 4 | −0.80 | 0.66 |

Four of five are off the sides. The fifth is horizontally in frame and its
crown is a third of a frame height *above* the top edge, so what the camera
sees of it is a wall whose top it never reaches.

No amount of temper, warmth or jag was going to fix that, and it is not a
mistake anybody could catch from a plan view. The finish camera is 36° vertical
on a 9:16 frame, which is **20.7° horizontal**, and an arc of radius 30 at 40
to 65 units subtends about ninety.

### The arc re-solved against the camera we already have

Part G says compose the world around the existing camera, so the arc was solved
against it: bearings 60°–120° at radius 22, which puts the five masses at
u = 0.93, 0.71, 0.46, 0.22 and 0.04 — spread across the whole width — and
`crown` comes down from 14 to 2 so the middle of the rim tops out just inside
the frame. `base` comes down with the radius so the masses still overlap into
one continuous rim rather than five towers. The lower rim is re-solved on the
same bearings so the two tiers are one composition.

Nothing about the camera moved, and no track, structure or stadium was added.

### And it is warm, because of a mechanism rather than a taste

The first re-solve put the rim on screen and it still read cold. **A warm
albedo cannot make a warm picture under a cool light**, and the light reaching
the rim's camera-facing side is `WorldBounce` at #35618F: the warm fill rakes
from bearing +58 and the finish camera stands to the south-west, so it sees
precisely the faces the warm light misses.

The fix is the brief's own listed lever — a basin practical. V25.1's third
finish lamp sat 44 units up-gorge at range 38, past the far horn, lighting
nothing in shot. The replacement stands 14 out and 12 along at range 40, which
puts every arc mass 11 to 18 units from it. World cull mask, like every lamp
here: it cannot reach the machine.

| | V25.1 | V25.2 |
| --- | ---: | ---: |
| finish rim, pixels with red leading green | 0.1% | **25.6%** |
| whole finish world, same | 0.8% | **8.5%** |
| finish rim, median red minus blue | −64 | **−46** |

The lower tier gets the shading response, no warmth at all and a raised
`shade_foot`, so the gorge falls away rather than filling in — the brief's
darker lower ravine, and what makes the two tiers read as two.

## 8. Part D — the vegetation

No more plants and no meaningful triangles per plant. V25.1 was right that the
fix is variety in the silhouette, and the finish crop says it did not go far
enough: every tier was a cone on a near-circular plan **with its apex on the
axis**, so a stack of them is a taller cone.

| option | what it does |
| --- | --- |
| `bough` 0.34 | the apex comes off the axis, and **the offset grows with tier index** — the largest lean lands on the topmost tier, whose apex is the only point a viewer reads as *the* point |
| `ragged` 0.24 | the skirt height varies per facet, so the lower edge of a tier is a line of drooping tips rather than a rim |
| `aspect` 0.34 | a per-plant width-to-height jitter, so two conifers in one stand are two trees |

And one kind: `snag`, a dead stem two thirds bare with two stub tiers, about
thirty triangles, and the only plant in the kit whose outline is a vertical
line. It is in the kit and in no cluster unless a profile names it — V25.2's
`trees.roles` does, one in nine.

`crop_tree.png` is the comparison. V25.1: three teal cones with straight edges,
bilaterally symmetric, in a void. V25.2: green rather than teal, leaning,
tiers with broken rims, varied widths, a snag, against a rock backdrop.

**Honest limit:** they read as *trees* now rather than as spikes, and at finish
distance the overall mass is still broadly conical. See §15.

## 9. Part H — the ground

Two changes, neither of them a texture.

**A material zone shades like the ground it is on.** `_patches` follows
`Terrain.height` across tens of units and each quad took its own face normal —
so a zone was a flat-shaded mosaic lying on a *smooth-shaded* terrain
(`course_terrain` emits `quad_smooth_auto`). At the finish that is 40% of the
frame, and it is the literal form of "the zones look like painted polygons":
they were the only polygons on the hillside that shaded like polygons. The
corner normals are now the terrain's own, sampled per corner, so a zone differs
from the ground in albedo and roughness and in nothing else — which is the
definition of a material zone. The outermost ring keeps its flat normals: that
is the vertical skirt, and a skirt that shaded like the ground it cuts into
would have no edge.

**The boundary is a curve.** 24 facets and 8 rings against 13 and 7, so the
coastline is not a 13-sided polygon at close range.

The hillside itself comes up two L\* and turns a few degrees off blue; the
zones keep their half-stop separation from it and gain a roughness spread, so a
zone boundary is a change of sheen as well as of hue.

## 10. Part I — what was removed

| feature | V25.1 | V25.2 | why |
| --- | ---: | ---: | --- |
| boulders | 46 | **42** | the smallest are under a unit across at thirty units |
| spires | 26 | **22** | V25.1's own verdict: the least silhouette per node, and it cut them once already |
| scarps | 36 | **33** | the site at (−48, −72) is behind the start backboard in every frame it appears in |
| everything else | — | unchanged | — |

Census total 316 → **305**. Nothing was added anywhere, and
`test_no_world_count_rose` fails if it ever is.

## 11. Motion review

Both worlds rendered end to end at 1080×1920 / 60 fps through V22.1's own
solved tracks: `full` (22.3 s), `choice` (fork to merge) and `preview`, then
cut into the five race sections and three side-by-side pairs.

* **0–4 s, start and mixer.** The background behind the rotor was a dark void
  with a few teal cones; it is now legible rock with a broken skyline and
  green stands. The mixer's own brightness is unchanged.
* **6–10 s, descent and obstacle.** This is the pass's clearest win. The
  descent's near cliff read as a mosaic of unrelated dark wedges and now reads
  as one turning mass. The obstacle's ground carries its slate pocket and its
  warm practical against a cool surround.
* **13–16 s, fork and branch.** More of the gorge is legible and the ravine
  has depth in it. The orange route is untouched and nothing warm was put near
  it — deliberately, twice over: the fork practical stays cyan.
* **17–22 s, finish.** The largest single change in the film. The upper third
  goes from a near-empty navy field to a warm-lit rock rim with a broken
  skyline, framed by green stands, over a dark lower gorge.

No new flicker, no crawling, no popping. The shading change is static geometry
under a moving camera, so there is nothing in it that can strobe.

## 12. Phone review

Sampled at 270×480 off both masters at 1.2, 3.6, 7.4, 8.9, 14.6, 17.2 and
19.8 s — `motion_strip` in the sheets, and `phone_sheet.png` for the thirteen
moments.

* cliffs read as single masses at phone size — the mosaic is what phone size
  used to amplify, because a small dark polygon has no internal cue at all
* the machine is the brightest and most legible object in every frame
* no dark blob swallows the track; the near ground is lighter than the track's
  own shadow side everywhere
* warmth is perceptible at the finish and at the obstacle and nowhere else
* the trees are a texture rather than noise: green, varied, and no longer a
  row of matched triangles along a crest
* the finish is visibly a different place from the rest of the world

Measured phone contrast (V25's own `noise` on the 270-wide reduction) is
**6.83 → 6.86 mean** over thirteen moments — unchanged to two figures.

## 13. Metrics

Pooled over the thirteen moments unless stated.

| measure | V25.1 | V25.2 | note |
| --- | ---: | ---: | --- |
| world cover (mean) | 38.7% | 40.4% | the world is more *visible*, not larger |
| machine headroom, L\* (mean) | 79.4 | **77.0** | the cost of the pass |
| machine headroom, L\* (min) | 61.5 | 61.4 | at the obstacle, both |
| marble separation ΔE (mean) | 51.159 | **51.157** | unchanged |
| flat-white clipping (mean) | 0.145% | 0.144% | unchanged |
| phone contrast (mean) | 6.83 | 6.86 | unchanged |
| midground dark pixels | 22.4% | **2.7%** | §3 |
| midground local value spread | 4.0 | 4.1 | §3 |
| hero rock local value spread | 28.6 | 26.3 | §4 |
| finish rim, red over green | 0.1% | **25.6%** | §7 |

**Headroom is the honest cost.** The machine is 2.4 L\* closer to its backdrop
on average, because the backdrop came up. It is still 61 to 84 L\* above it —
the machine's body is L\* 85 and the world's lit rock is in the twenties — so
the hierarchy is not in question, and the 95th percentile of every frame is
unchanged to within a level: the pass raised the shadows and did not touch the
highlights.

### Parallax, and why the image-space test cannot adjudicate this pass

V25.1's §15 records the block matcher failing on flat-shaded rock: a 41-pixel
template inside one facet has no contrast and is discarded, so bands covering a
third of the frame report "fewer than two patches". **V25.2 breaks the same
measure a second way** — a tempered surface is a smooth gradient with no
distinctive feature, so the correlation peak lands on zero, and `--stage
parallax` reports `0px` on the final dive for a camera that is plainly moving.

So the verdict is the shading-blind instrument: the world's own form positions,
projected through the solved camera at both instants.
`docs/validation/sloped_race_v1/v252_world/geometry.txt`:

| move | foreground | vegetation | ridges | walls | spread |
| --- | ---: | ---: | ---: | ---: | ---: |
| obstacle_pan | 37 px | 31 px | 52 px | 66 px | **2.2×** |
| fork_swing | 55 px | 41 px | 137 px | 147 px | **3.6×** |
| branch_cross | 328 px | 303 px | 460 px | — | 1.5× |
| final_dive | 1 px | 1 px | 2 px | — | 2.4× |
| preview_dolly | 128 px | 130 px | 55 px | — | 2.3× |

**Identical for both worlds, band for band and pixel for pixel**, which is what
it must be: parallax is a property of where the forms are and where the camera
goes, and this pass moved neither. A test asserts the two tables are equal, and
it would fail if anything in this pass had quietly moved geometry.

## 14. Performance

| | V25.1 | V25.2 | change |
| --- | ---: | ---: | ---: |
| meshes | 2307 | **2284** | −23 |
| triangles | 643,302 | **650,556** | +1.1% |
| ms/frame (median of three runs) | 315 | **337** | +7% |

The triangles come from the shoulders and the finer material zones; the meshes
fall because eleven objects went. `temper` and `shade` cost nothing at render
time — they are baked into the mesh at build time — and `soft_light` is one
extra term per light in a shader that already runs.

+7% of render time for the whole pass is inside the brief's budget by a wide
margin.

## 15. Tests

`tests/test_sloped_v252_world.py`, 40 assertions in six groups:

* **Nothing reached the race.** Seed 5432, V22.1's two solved tracks, the
  locked replay, `course_terrain.height` line for line, the layout tables, and
  every comparison second inside the edit. The profile names no field the
  physics reads.
* **Nothing reached the landform.** No collider type appears in any changed
  module; `_patches` reads `Terrain.normal` and `Terrain.height` and writes
  neither; every world mesh is on the world light layer and every world
  practical carries the world cull mask.
* **The earlier passes still render.** Every profile shipped before V25.2 is
  registered, and none of them names any of the twenty-two opt-in fields. Every
  new generator option is asserted to default to a no-op, and the untempered
  path is asserted to be the *same shared emitter* rather than an equivalent
  one.
* **The pass is a delta.** It extends V25.1, no count rose, no landmark was
  invented, only the three sites Part E and F name carry anything but a
  `shape`, and the wall ring, both ridge bands, the spire zone and the ravine
  restate no position.
* **Machine and environment stay independent.** No machine surface is in the
  world profile; the four new palette fields appear in neither V21's retune nor
  any machine pass.
* **The instruments are sound.** Every painted surface is in exactly one band;
  the three new measures return `nan` rather than zero on an empty band; the
  spread measure is checked against a known input; and the analytic parallax
  field is asserted identical to V25.1's.

Two tests in other suites were updated rather than worked around:

* `test_sloped_v251_world.test_the_flora_kit_has_the_five_named_plants` asserted
  the kit was *exactly* five. It now asserts V25.1's five are all present and
  that **V25.1's own cluster composition names none but those five**, so a
  plant added for a later profile cannot appear in a V25.1 render. That is the
  property V25.1 actually needs.
* `test_sloped_v23_machine.OTHER_CALLER_FIELDS` gained the four new palette
  fields, with the reason: each *enables* a material feature, which is exactly
  why a machine pass must not be allowed to name one.

### Reproducibility, proved rather than asserted

Not "the options default to off, so the old renders must be fine" — the old
renders, re-run and compared byte for byte.

**V25.1 renders byte-identically from this branch.** Thirteen frames across
both tracks, md5-compared against the same frames rendered before any change in
this pass, and again after all of them: all thirteen identical. The two labs
render `aurora_valley_v251` into different directories from the same flags and
produce the same bytes.

**V25 B renders byte-identically across worktrees.** Ten race frames rendered
here, md5-compared against the frames sitting in `wt-v25-world` — rendered on
the V25 branch, before the rock kit, the vegetation kit or any of this
existed. All ten identical, and the cost line still reads 2252 meshes and 693k
triangles.

**V23 is untouched by construction and the V25 B proof covers the reason.**
`aurora_valley` carries no `world` section, so `environment_world.build`
returns before it reaches any changed line, and `world_rock` and `world_flora`
are reachable from nowhere else. The only shared file V23 does run through is
`lab_palette`, and V25 B exercises it under a full world.

### The wider suite

Every `tests/test_sloped_*.py` file: **1264 passed, 139 skipped, 20 failed, 39
errors** — and the twenty failures and thirty-nine errors are **the same set,
file for file and name for name, as `origin/v251-world-art-polish` produces in
its own worktree**. They are missing optional dependencies (`pybullet` and
friends) and pre-existing failures. This pass adds none.

## 16. Remaining weaknesses

1. **The trees are better, not solved.** `bough`, `ragged` and the growing lean
   break the outline and the stand now reads as varied vegetation, but at
   finish distance the overall mass of a conifer is still broadly triangular.
   Genuinely fixing that means a branch structure, which costs triangles the
   brief did not offer and which V25's own argument says a phone will not read.
2. **The lower half of the finish frame is still a large flat ground wash.**
   About 40% of the payoff frame is the hillside falling into the gorge. It is
   *wanted* dark — the brief asks for a darker lower ravine — but it is
   featureless dark, and the heightfield is locked, so the only levers left
   were albedo, roughness and the zones. All three were used and the region is
   still the weakest part of the strongest shot.
3. **Headroom fell 2.4 L\*.** Argued in §13 and not disguised. A reviewer who
   wants it back should lower the four rock albedos by two L\* together, not
   lower `soft_light`: the floor is what killed the mosaic.
4. **The obstacle's identity is a ground and a lamp, not a place.** The
   segmentation in §6 is the reason, and it is a camera fact rather than a
   world one. A canyon that shot could actually see would have to stand where
   the racing line is.
5. **The image-space parallax measure is now blind in two directions.** It
   loses flat facets and it loses tempered gradients. The analytic instrument
   covers this pass, but it cannot see occlusion, so a future pass that changed
   what is *in front of* what would have no good measure at all.
6. **`crease` is one number for the whole world.** It works because facet count
   correlates with form width in this kit. A kit entry that broke that
   correlation would need its own threshold, and nothing enforces the
   correlation.

## 17. Recommendation

**Ship V25.2 as the world, subject to watching the motion proof.**

Against the brief's ten success criteria:

| | criterion | verdict |
| --- | --- | --- |
| 1 | cliffs no longer read as dark polygon mosaics | **yes** — 22.4% → 2.7% dark with the local spread unmoved |
| 2 | hero rocks have better silhouettes | **yes** — five formations, three silhouette options, spent unevenly |
| 3 | cool but no longer monochromatic | **yes** — a hue progression with depth and a warm finish |
| 4 | vegetation looks designed | **partly** — see §16.1 |
| 5 | the obstacle has local identity | **partly** — a stone and a light, not a place; §16.4 |
| 6 | the finish feels like a destination | **yes**, and it is the biggest change in the film |
| 7 | the machine remains the visual hero | **yes** — 61 to 84 L\* of headroom, highlights untouched |
| 8 | parallax remains strong | **yes** — identical to the pixel |
| 9 | phone readability remains good | **yes** — contrast unchanged, legibility better |
| 10 | full motion looks more premium than V25.1 | **yes** |

Two of the ten are partial and both are recorded above rather than argued away.

**Do not merge and do not integrate with V24 until the full motion proof has
been watched.** The stills and the numbers agree, and neither is the test the
brief asked for.

---

## Outputs

    docs/validation/sloped_race_v1/v252_world/   sheets, crops, measures
    output/sloped_race_v1/v252_world/            renders and clips
    exports/v252_world_final_lookdev/            what a reviewer is handed

Motion: `exports/v252_world_final_lookdev/clips/full_aurora_valley_v252.mp4`
against `full_aurora_valley_v251.mp4`, the five sections in `clips/sections/`,
and three side-by-side pairs in `clips/pairs/`.

Reproduce:

    python tools/sloped_v252_profiles.py
    python tools/sloped_v252_world.py --stage all --godot PATH
