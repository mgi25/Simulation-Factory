# V25.1 — the same world, designed rather than generated

**Status: built, measured, awaiting review. Not merged. Not integrated with V24.**

V25.1 is an art pass over V25 B. The race is the same race: same seed, same
replay, same solved camera track, same edit, same cues, same 1340 frames, same
machine. The world is in the same places at the same density. What changed is
**what the forms in it are made of**.

    --environment=aurora_valley_v251     the world, rebuilt from two kits
    --machine=v23b                       the machine, V23's, unchanged

Branched from `origin/v25-world-quality` (`333703e`). V24 is untouched and is
not a base for anything here.

---

## 1. Why V25 was structurally successful

V25's problem was that there was nothing between the near ground and the sky,
and it proved that with a number: on five of thirteen comparison frames V23's
world was **under one per cent of the picture**, and in four of five camera
moves there was not one world depth band on screen with enough of itself
visible to track.

V25 fixed that, and the fix holds here unchanged. Every radius, bearing, count
and site in this pass is B's. The measured world cover is the same to within a
point (39.1% → 38.7% mean over the thirteen moments), the five depth bands are
the same five bands, and the recession between them is the same argument about
the same numbers.

**Nothing in this pass is about density.** The brief locks B's layout as the
target and a test asserts that no count rose.

## 2. Why it still looked prototype-like, stated exactly

Three causes, and the first is worth more than the other two together.

**Every rock in the world came out of one function.** `hero_world.smooth_mass`
is

    radius(u, v) = base × taper(v) × noise(u, v) × strata(v)

with averaged normals everywhere. That is a noise-displaced dome, and a
noise-displaced dome has three properties a designed rock does not:

* **No planes.** Smooth normals mean the shading field is continuous, so no
  two parts of the surface catch the key differently enough to read as
  separate faces. A cliff is a thing made of planes meeting at edges; this is
  a thing made of gradients.
* **A round silhouette.** Three octaves of noise on the radius move the
  outline by a few per cent. The outline is still a circle in plan and a dome
  in elevation, and at phone size the outline is all there is.
* **No intent.** Every part of the form is statistically identical to every
  other part — no dominant mass, no secondary mass, no break.

A full-resolution crop of the split frame makes the case without any argument:
`docs/validation/sloped_race_v1/v251_world/pair_split.png`.

**The near ground was one material.** V25 recorded this as its own weakness 2
and worked around it with geometry. The hillside is a third of several frames
and it was a single painted blue surface in all of them.

**A hundred and fifty mid-sized objects were scattered across it.** Sixty
scarp slabs, ninety anchor parts, seventy-two boulders — and at the distance
the race cameras stand, a rounded box with no silhouette of its own reads as a
box. The preview and the split frames were fields of dark crates.

## 3. The rock kit

`godot/assets/marble_machine/environment/world_rock.gd`. Eight forms from one
generator, and eight is the whole kit deliberately — a kit goes crude by
growing an entry per site until nothing is reusable.

| kind | what it is | where it is used |
| --- | --- | --- |
| `cliff` | tall, two ledges, broad flat crown, two buttresses | the near ridge band, the finish basin |
| `block` | squat, one ledge, wide top | boulders, basin horns |
| `ledge` | low and wide, read for its horizontal | the scarps, the east-wall mesa, the fork's low post |
| `needle` | vertical spire, almost no top | the skyline spires, the gorge teeth, the fork's high post |
| `slab` | leaning broken plate, two flats | boulders |
| `boulder` | a chunk, few facets, strong lobe | boulders |
| `wall` | long, many facets, grooved | the ravine banks, the merge narrows |
| `mountain` | wide, low, crowned with a ridge line | the far ridge band, the valley walls |

A form is three separable parts, each answering one of the three failures:

**plan** — `K` radii round the form, composed rather than sampled: one dominant
lobe plus a second and third harmonic (a single cosine is an ellipse, and an
ellipse is still a smooth closed curve — three harmonics in phase give a mass
with a front, a flank and a back), then one or two *chorded flats* where a run
of consecutive facets is pushed onto a straight line, then one or two hard
*notches*. The plan is the silhouette and it is the same plan the whole way up,
so a form has a shape rather than a different shape per tier.

**profile** — a piecewise taper with hard ledge steps. A ledge is two rings at
almost the same height with a step in radius between them; the quad between
them is nearly horizontal, so it faces up, takes the key square on, and the
face below falls into its shadow. That is a different mechanism from V25's
`strata`, which is a 4.5% sine ripple — a ripple has no horizontal anywhere on
it, so it never catches a light and never casts a line.

**frame** — a lean, a twist, and a second *crown* plan the base plan blends
into with height, so a form is neither a prism nor a solid of revolution.

Every quad is emitted with one face normal through `Geometry.quad_auto`.

### The correction the probe sheet forced

The first build stepped the radius **uniformly** at each ledge, and
`tools/sloped_v251_kit.py`'s contact sheet said what that is: a stack of
cylinders. A wedding cake. Exactly the "repeated rectangular prism" the brief
bans.

A real shelf is a *partial* feature — it runs along one aspect of a cliff, dies
out at a corner, and the next shelf up starts somewhere else. So a ledge here
owns an arc: a start facet and a span of a third to three quarters of the
circumference, and the step applies only inside it. Two ledges on one form
therefore almost never share an aspect, which is what makes them read as two
events in the rock rather than as a repeat. That is also why the profile
returns a per-facet scale rather than one number.

### And the secondary mass

The brief's rule for a hero formation is one dominant mass, one secondary mass
and one or two asymmetric breaks, and the first two of those cannot come out of
a single solid of revolution however it is faceted — a shape with one axis has
one mass by construction. So a form may carry **buttresses**: smaller shells of
the same kind at 38–62% of the height, pushed out to the foot's own edge and
welded into the same surface. Interpenetrating rather than boolean: two closed
opaque shells that overlap render as their union with no seam, because the
depth buffer does the union for free.

### It is cheaper than what it replaces

`smooth_mass` at V25's settings is 26 facets × 14 tiers × 2 triangles plus a
26-triangle crown: **754 triangles**. A `cliff` here with two buttresses is
about **420**. The whole world is 693k triangles in B and **643k** in V25.1, on
2% more meshes — see §17. The quality was never in the triangle count; it was
in where the edges are.

## 4. The near ground

`environment_world._patches`. Eleven stylised material zones laid over the
heightfield, 28 to 34 units across.

**Why not a texture.** The brief's rule and this course's own style lock:
variation at large spatial scale, nothing high-frequency, no photographic
noise. A tiling rock texture on this ground would read as dirt on a toy at
exactly the moment the machine has to read as moulded.

**So: geometry that is a material.** A patch is a mesh that follows
`Terrain.height` across tens of units, lifted ten centimetres, painted a
different value and roughness — a gravel shelf, a damp apron below a ledge, a
soil bench, the warm-neutral ground inside the finish basin. It is the same
surface the terrain has, so it cannot be seen as an object; what is seen is
that the ground changes material there.

Four new surfaces, and each is within about four L\* of `slope_earth` and
separated from it by **hue and roughness** rather than by value. A zone much
lighter than the hillside is a painted patch; a zone half a stop away with a
different sheen is a change of material.

Two details make it read rather than z-fight: the rim drops *below* the terrain
rather than ending in mid-air, and the plan is an irregular polygon so a
boundary is a coastline rather than a disc.

### The skirt correction

The first build spread the outermost ring a whole step past the second-
outermost and dropped it — a shallow apron a few units wide cutting down
through a bumpy heightfield. Where the ground is convex the intersection came
back as a torn, flame-shaped edge. The last ring now stands at the *same
radius* as the one inside it and simply drops, so the boundary is the polygon's
own edge and what is below it is buried.

### And the one zone that had to break the rule

`world_ember` is the ground inside the finish basin, and it is the only zone
allowed to separate by value as well as by hue. At #332F33 — four L\* above
`slope_earth`, like every other zone — it was **invisible in the one frame it
exists for**: the finish camera reads the mesa at forty units at a grazing
angle through fog, and all three of those flatten a four-L\* step to nothing.

At #3E3739 it is measurable. Inside the zone the finish frame renders RGB
(30.2, 45.0, 61.4); immediately outside it, (28.7, 55.1, 80.8); the same pixels
in V25 B, **(8.9, 44.0, 80.0)**. The red channel more than triples and the blue
falls by a quarter. A zone rule that is right for nine sites can be wrong for
the tenth.

## 5. The vegetation kit

`godot/assets/marble_machine/environment/world_flora.gd`. Five plants:
`conifer`, `spruce`, `hero`, `shrub`, `tuft`.

V25's argument for one cone was that at 270 pixels a modelled branch structure
is four dark pixels either way, so a silhouette is the correct amount of tree.
That argument is half right and the half it gets wrong is the expensive half: a
silhouette *is* all a viewer reads at phone size, but 188 copies of **one**
silhouette, and that silhouette a cone, is what the review saw and called
spikes. In the V25 finish frames they line up along the crest as a row of
identical dark teal triangles.

The fix is not detail, it is **variety in the silhouette at the same triangle
cost**: three or four stacked crown tiers give a stepped outline rather than a
straight one; tiers of different widths and drops mean two trees from one
generator differ; a trunk is eight triangles and is the difference between a
tree and a shape; a lean and an off-centre crown break the bilateral symmetry.
A `conifer` is 65 triangles against V25's cone at 88.

The hero form took one correction. It was the *widest* plant as well as the
tallest, and the probe sheet called it a parasol. A hero tree is taller than
its neighbours, not fatter: `spread` came down and `trunk` and `drop` went up,
so what distinguishes it is a long bare stem under a narrow crown.

### Placement

26 clusters rather than 40, about 117 plants against 188, and **a cluster is
composed rather than scattered**: the first plant is the kit's `hero` near the
centre, and the rest fall on a ring whose radius grows with index, so the small
forms end up at the edges where a stand of trees actually thins. `min_normal`
went from 0.72 to 0.80, which puts a cluster on a shelf or a bench rather than
on a face — the brief's "following ledges / protected areas", expressed as the
one property of the terrain the builder can read.

## 6. What was removed

| feature | V25 B | V25.1 | why |
| --- | ---: | ---: | --- |
| crest teeth | 169 | **0** | the kit's own ridge crowns and buttresses do what they were bolted on to fake |
| scarp slabs | 60 | **36** | five rounded boxes per site read as a pallet of crates |
| spires | 38 | **26** | the feature that bought the most count for the least silhouette |
| boulders | 72 | **46** | a field built from one preset is a repeat however many there are |
| trees | 188 | **117** | five silhouettes instead of one |
| anchor bodies | 90 | **55** | see below |
| landmark forms | 10 | **16** | three of V25's were in no frame at all; see §8 |

Net: 602 world nodes to **530**, and 693k triangles to 643k. The brief's
Part Q, applied.

## 7. The foundations, and two corrections in opposite directions

V25's anchor was a sunken disc, four kerb blocks on a half arc and a graphite
sill, and its own notes record the correction that got it from seven blocks to
four. The motion proof says that correction did not go far enough: at every
wide framing the anchors read as **a field of scattered dark cubes** under the
track. Three causes, each fixed here:

1. **The pad was invisible.** A disc sunk almost flush in `world_scarp`, which
   is *darker* than the hillside it sits in, shows a rim of nothing — so the
   only thing an anchor contributed was its blocks, and a block with no
   platform under it is a box on a hill.
2. **The blocks were darker than the ground.** A small dark shape on a lighter
   ground reads as a hole, and a row of holes reads as debris. Engineering
   concrete should be the one thing out here that is *lighter* than the rock,
   because that is what concrete is.
3. **Four separate arcs are four objects.** Whatever the gaps were meant to
   say about masonry, at forty units they are four shapes.

A **bench** is instead a level shelf cut into the slope, one continuous
retaining wall along its downhill lip with the seams cut into its own top edge
as notches rather than as gaps between bodies, and a small graphite sill under
the pier. Five meshes per site against six, and one silhouette instead of five.

**And then it went too far the other way.** The first V25.1 render built the
same fifteen benches out of `world_concrete` at #464D5C — three stops above the
hillside — and they came out as sixty **pale** boxes strewn across the near
ground, brighter than any rock in the frame and second only to the machine. A
worse version of the failure they were meant to fix.

A foundation is read by its shape and its shadow, not by its value. The
concrete is now #343B49, about four L\* above `slope_earth`; the footprint is a
third smaller; and the interval went from 15 units to 20. Eleven benches
instead of fifteen.

Twenty-four units was tried first and gave **four**, which the instrument said
were visible but which is too few to read as how this machine stands on this
hill. Twenty is the setting where every one of the thirteen frames has a bench
in it and no frame has a row of them.

## 8. The landmarks, and the finding this pass is built on

V25 sited its landmarks "from the layout's own `nodes` table, so a landmark is
at the place it is named for by construction". That is true and it is not
sufficient, because **the camera named for a place is not looking at that
place** — it is tracking the pack, which by the time a cut is named for a node
has usually gone past it, and it is looking *down-course* at whatever is
beyond.

Projected into the thirteen frames by `tools/sloped_v251_sites.py`, three of
V25's five landmarks are in **no frame at all** — not their feet, not their
middles, not their crests. The start butte and the obstacle spires stand on the
west uphill wall, which no camera on this course ever sees. Four of the first
ten material zones were in no frame either.

So every form is now sited where the instrument says it lands:

| form | kind | where | frames that see it |
| --- | --- | --- | --- |
| `east_wall` | `ledge` mesa at (46, 2) | across the gorge | start, mixer, descent, fork approach, split, preview |
| `gorge_teeth` | paired `needle`s at (48, −20) | the gorge's east lip | descent, mixer |
| `split` | `gate`: `needle` + `ledge` | either side of the fork | branch, merge, obstacle, preview ×2 |
| `merge_narrows` | paired `wall`s at (−17, 54) | at the rejoin | merge |
| `finish` | `basin`, five masses | wrapping the payoff | seven of thirteen |
| `finish_floor` | `basin`, four masses | in the gorge below | seven of thirteen |

**The east wall is the most valuable site on the course**: inside six frames
and near an edge in every one of them, between u = 0.62 and u = 0.85. That is
what a framing element should be — present in half the film and in the way of
none of it. Its broad flat crown is deliberate: the whole start sequence is
verticals, and one long horizontal high in the frame is what settles them.

The obstacle has no landmark, and that is a finding rather than an omission.
Its camera is a 25-unit machine shot whose entire visible world is the finish
bowl ninety units down-course; there is no placement in that frame that is not
already inside the finish basin. The obstacle's distinctive element is the
spinner.

### The merge mark moved twice, and the second time for a reason no rule could catch

The first placement stood 11.3 units from the final cut's camera path against a
16-unit keep-out; the builder rejected it and said so. The second cleared every
keep-out and then turned up in the **finish approach** as a black wedge down
the left edge, partly over the checkered deck — a mass the camera never goes
near but looks straight past.

A keep-out is a rule about where a camera *goes*. Nothing in a profile can
express where one *looks*. It was found by rendering the frame and disabling
the feature, and it is the reason the siting tool exists.

## 9. The fork

Part I asks the landscape to communicate "two different ways" without leaning
on the cyan and orange track lighting. V25's gate already used a height ratio
and its own verdict was that the fork reads as two rocks rather than as two
ways.

The two posts are now different **kinds**, not one kind at two heights: a
vertical `needle` on one side and a broad stepped `ledge` mesa on the other,
with the low side 1.55× wider. Two kinds of country either side of the choice.

## 10. The finish basin

The highest-priority art change in the brief, and the place where a plan-view
judgement is most wrong.

**The finish stands on a promontory.** The mesa is at y = −2 and the ground
falls to −82 within forty units in every direction the finish camera looks. An
arc of five seventy-unit masses placed round the node therefore tops out at
−31 — thirty units *below* the deck, invisible from a camera looking down at
the deck. That was the first build and it is V25's own "a radius means nothing
until it is compared with the camera envelope", one step further in.

So the basin is specified by its **crest**: `crown` names the absolute y the
arc's back should reach, fourteen above the finish deck, and each mass grows
from wherever the ground actually is to get there. The far wall comes out about
eighty units tall and the near horn about twenty-five, and the two read as one
rim rather than as a tall rock and a short one. The arc runs 26° to 158°, which
is the wedge both finish cameras look into and is open on the approach: nothing
in it can come between a camera and the FINISH board.

**And a second, lower rim.** The high arc puts rock across 59% of the top third
of the finish frame and *nothing* below it — measured, not guessed: a render
with the landmarks disabled differs from one with them in zero pixels below
y = 700. The lower arc stands on the gorge floor at two thirds the radius and
tops out twelve *below* the deck, in `world_damp`, the darkest surface in the
world. The brief asks the finish for "a dark lower ravine beneath"; a dark
ravine with form in it is a different picture from a dark ravine with nothing
in it.

The third part is the ground: the `world_ember` zone of §4, measured at RGB
(30.2, 45.0, 61.4) against V25 B's (8.9, 44.0, 80.0) in the same pixels. Warm
here means *not blue* — in a frame where every other surface carries a cyan
cast, a neutral reads as warm without a single orange pixel being spent, and
without competing with the gold chute or the FINISH board.

## 11. Lighting, and a correction to V25's own record

V25's weakness 5 says "there is no warmth in the world at all". **That is not
true**, and the first version of this profile acted on it and made things
worse.

V23's `aurora_valley` already carries a `WorldWarm` — #FFAE62 at energy 0.9,
raking from bearing +52, opposite the cool `WorldKey` at −78. The first V25.1
profile set `WorldWarm` to 0.34 at bearing −104 "to add warmth", which was in
fact **cutting the existing warm fill by 62% and pointing it round onto the
key's own side**, where it filled nothing. A full-resolution crop of the split
frame came back with a near-black left half.

A flat facet has no shading gradient by construction, so the side of a form the
key misses is one flat value — and if the fill does not reach it, that value is
black. Smooth rock hides a missing fill; faceted rock cannot.

The shipped rig is therefore three dials and one new light:

| light | V25 B | V25.1 | why |
| --- | --- | --- | --- |
| `WorldKey` | 1.65 | 1.58 | pays for the fill; the world's total light may not rise |
| `WorldWarm` | 0.90 @ +52 | **1.05 @ +58** | V23's own bearing and colour, 17% more of it |
| `WorldRim` | 0.55 | 0.66 | a rake has edges to find now; against `smooth_mass` it had none |
| `WorldBounce` | — | **0.55 @ +208** | new; see below |

**The new light exists because of a measurement.** The world rig has four
directional lights at bearings −78, +26, +58 and +96 — a 174° arc — and
everything facing the other 186° is lit by ambient alone. `smooth_mass` hides
that completely: its normals vary continuously, so a large face is never all on
the wrong side of every light. A flat facet has one normal, and a facet
pointing south is *entirely* in the gap. `WorldBounce` is a low cool rake from
the middle of that hole — cool rather than warm on purpose, so the warm fill
stays one direction and reads as a break rather than as a tint.

Every one of these is on cull mask 2. None of them can reach the machine.

## 12. The value tail: four hypotheses, three of them wrong

Flat shading changes the *distribution* of world values, and it took four
attempts to say correctly how.

Segmented off the marker render and pooled over the thirteen moments:

| | V25 B | V25.1 |
| --- | ---: | ---: |
| world cover | 39.1% | 38.7% |
| **median world grey** | 22.8 | **21.8** |
| **world pixels under grey 12** | 14.2% | **20.3%** |

The median is unchanged and the dark tail is six points fatter. Per band, at
the three frames with the most world in them:

| band | dark %, B → V25.1 | median grey, B → V25.1 |
| --- | --- | --- |
| terrain | 6.5 → **4.6** | 27.0 → **27.7** |
| foreground | 20.9 → **7.5** | 18.0 → **43.0** |
| walls | 7.9 → **0.0** | 29.3 → **47.5** |
| ranges | 5.6 → **4.3** | 24.0 → **24.5** |
| **ridges** | 22.6 → **42.2** | 17.0 → **14.3** |

**Every band got lighter and more readable except the midground ridges**, which
got darker. Four things were tried and the first three did not work:

1. **Restore and raise the warm fill** (§11). Real and necessary, and it moved
   the pooled tail by under a point.
2. **Add a back-fill from the unlit 186°.** Swept at 0.55, 1.1 and 1.7; the
   dark share of the worst frame moved 45.1% → 44.7%. Then tested with a
   *red* light at energy 6.0, which put 5.3 of red into the region — the
   faces were not facing the back-fill either.
3. **Bury the foot.** Every world light points downward, so a `Vector3.DOWN`
   cap is lit by nothing; the kit's flat foot fans were exposed wherever the
   ground fell away. Replacing them with a buried skirt and a vertical wall is
   correct and is kept — and it moved the pooled tail by 0.1 of a point.
4. **Slope the ridge faces.** The ridges used the kit's two most vertical
   forms, and a near-vertical flat facet is a binary: its normal is horizontal,
   so it either faces a light and takes the full cosine or faces away and takes
   nothing. Giving them `cliff` and `mountain` (taper 0.46 and 0.54, batter
   0.58 and 0.60) is the right art as well — the progression cliff → mountain →
   mountain-with-a-bigger-ridge across 100, 190 and 300 units is the brief's
   Part M. It moved the pooled tail from 20.8% to 20.3%.

**The honest conclusion is that the tail is intrinsic to flat shading.** Each
facet has one value; a smooth surface produces a continuum and a faceted one
produces a histogram, and some of its bars are low. No lighting dial removes
that, as three falsified fixes now demonstrate. What the pass buys for it is
that the near and far bands became *much* more readable — the foreground's
median grey went from 18 to 43 — and what it costs is a darker, higher-contrast
midground. That is what "controlled form lighting" looks like against a
midground that was previously a flat mid-value wash, and it is stated here as a
characteristic rather than defended as a win. A reviewer who wants it dialled
should raise `WorldBounce` and lower the ridge bands' `batter` together.

## 13. The ravine and the water

**Kept, and the decision is measured rather than inherited.** The marker render
puts the ravine band on screen in three of the thirteen moments — 15.3% of the
branch frame alone. What makes the water read is not reflection but the
contrast between one smooth plane and the broken rock around it, and V25.1
sharpens exactly that: the seven banks are now `wall` kit forms with ledges and
buttresses instead of smooth domes, painted `world_damp`, which is the darkest
surface in the world.

The finish's lower rim (§10) is the same idea applied where the gorge was
emptiest.

## 14. Atmosphere

Unchanged. V25's fog — #15293F at energy 0.55, density 0.0038, pooled at the
gorge lip with `height -40` and `height_density 0.030` — was authored against
rock at a hundred units and is correct for rock at a hundred units. V23's gorge
mist decks are untouched, for the reason V25 gave: they took two attempts to
get out of the sky and their numbers are not this pass's to move.

No slab haze was added. V23 proved this course cannot use any and V25 did not
retest it; neither does this.

## 15. Parallax, and a second instrument

Part N is that the parallax V25 solved must survive. It does, and proving it
took a new measure.

**The image-space test loses bands on flat-shaded rock.** `band_shift` discards
any 41×41 template whose standard deviation is under `TEXTURE_FLOOR`, because a
correlation peak on a flat field means nothing. That rule is right, and against
`smooth_mass` it costs almost nothing — averaged normals put a gradient on
every square inch. **A flat facet is one value**, which is the whole point of
it, and at a distance where a facet spans more than forty-one pixels a template
lands wholly inside one.

`docs/validation/sloped_race_v1/v251_world/texture.txt`, measured:

| move | band | world | sites | pass | median sd | cover |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| fork_swing | ridges | V25 B | 9 | 4 | 1.19 | 25.8% |
| fork_swing | ridges | **V25.1** | 9 | 3 | **0.09** | **28.9%** |
| fork_swing | walls | V25 B | 9 | 7 | 3.42 | 6.5% |
| fork_swing | walls | **V25.1** | 7 | **0** | 0.54 | 2.8% |
| branch_cross | foreground | V25 B | 9 | 9 | 4.17 | 19.4% |
| branch_cross | foreground | **V25.1** | 9 | 8 | **7.98** | 10.3% |

Cover is unchanged or higher and trackability collapses — and the *foreground*
gains contrast, because at close range a 41-pixel window straddles the hard
edge between two facets. So the measure's failure is a function of facet size
against patch size, not of the world.

**The second instrument has no such failure mode**, because it never looks at a
surface. `tools/sloped_v251_sites.py --parallax` takes the positions of the
world's own forms, projects each through the solved camera at both instants,
and reports the median pixel displacement per band. Exact and shading-blind:

| move | foreground | vegetation | ridges | walls | spread |
| --- | ---: | ---: | ---: | ---: | ---: |
| obstacle_pan | 37 px | 31 px | 52 px | 66 px | **2.1×** |
| fork_swing | 55 px | 41 px | 137 px | 147 px | **3.6×** |
| branch_cross | 328 px | 303 px | 460 px | — | 1.5× |
| final_dive | 1 px | 1 px | 2 px | — | — |
| preview_dolly | 128 px | 130 px | 55 px | — | **2.4×** |

Three or four bands moving at 1.5× to 3.6× different rates through every chase.
`final_dive` is near zero for every band because the camera is nearly parked
there — which is V25's own finding, reproduced by a different instrument.

The ordering is not near-to-far and is not expected to be: every race camera is
tracking the pack, which pins a point at the pack's own distance and makes
image velocity grow in *both* directions from it. V25 established that and it
is unchanged.

A test asserts that three of the five moves keep at least three bands with at
least a 1.4× spread.

### And an instrument bug, caught the way they always are

The siting tool's first version read the camera frame stamped with the same
number as the moment. **An output second is not a replay second**: V22.1's edit
omits 1.95 s of replay in six windows, so at the descent the tool was reporting
a camera 2.15 s of moving chase away from the frame the sheet shows. Two
landmark placements were authored against that.

It was caught by an assertion that had to be true and was not — the start
camera looks at the start node dead centre, and the tool said it did not. The
edit map is now a port of `sloped_race_scene._replay_at`, and a test checks
three of its values.

## 16. Motion and phone review

**The motion proof** is the whole race end to end, 22.317 s at 60 fps at
1080×1920, plus the two shorter spans, in
`output/sloped_race_v1/v251_world/clips/` and copied to
`exports/v251_world_art_polish/clips/`:

| clip | span | variants |
| --- | --- | --- |
| `full_*.mp4` | the whole race, 1340 frames | V25 B, **V25.1** |
| `choice_*.mp4` | fork to merge, 229 frames | V25 B, **V25.1** |
| `preview_*.mp4` | the course preview, 210 frames | V25 B, **V25.1** |

and the five race sections the brief asks for, in `clips/sections/`, both
variants each — `1_start` (4.55 s), `2_descent` (2.97 s), `3_obstacle_fork`
(7.07 s), `4_branches_merge` (2.17 s), `5_final_finish` (5.57 s).

**The sections are cut out of the finished masters rather than rendered.** A
section rendered separately would be a second render of the same frames, and
two renders of one span are not guaranteed identical across a driver reset —
this branch measured a 7/255 drift on 0.44% of pixels between sessions, and
byte-identical output within one. Slicing the master makes a section the
master's own frames by construction. They are re-encoded rather than
stream-copied, because a copy can only cut on a keyframe and would slide a
boundary by up to a second.

The kit itself is photographed on its own, before it is wired into the course,
by `tools/sloped_v251_kit.py` — `kit_rock.png`, `kit_flora.png` and
`kit_silhouette.png` in the validation directory. Two of the corrections in
this document were found there and nowhere else: the wedding-cake ledges (§3)
and the parasol hero tree (§5). A boulder at thirty units is forty pixels tall,
and a change to its plan that is obvious on a turntable is invisible in a race
frame.

Two of the corrections in this document were found only in motion or only at
full resolution, and neither was visible in a contact sheet: the pale benches
(§7) and the near-black split background (§11).

**At 270×480** — `phone_sheet.png` — the V25.1 column is a darker, cleaner
picture with fewer discrete objects in it. The one number worth having is
whether the world has become noise. Mean local contrast over the lower 70% of a
270×480 frame, averaged over the thirteen moments: **7.00 → 6.83**. It went
down, which is what removing 150 scattered mid-sized objects and replacing 169
crest teeth with ridge crowns should do.

Marble separation, by projection rather than by eye: median dE **49.9 → 49.9**,
unchanged. Worst-frame flat white 0.571% → 0.601%, a tenth of the V21
readability pass's own budget.

## 17. Performance

| | V25 B | V25.1 |
| --- | ---: | ---: |
| mesh instances | 2252 | **2307** (+2%) |
| triangles | 693k | **643k** (−7%) |
| world nodes built | 602 | **530** |
| ms/frame, thirteen stills | 359 | **294** |
| ms/frame, `choice` clip (229 frames) | 333 | **267** |
| ms/frame, `preview` clip (210 frames) | 321 | **256** |

**Triangles fall and meshes rise slightly**, and both have the same cause: a kit
form is a third the triangles of a `smooth_mass`, and a tiered conifer is four
meshes where a cone was one. Every world material is still shared across every
instance of its band.

Frame time is 18–20% lower on three independent spans. V25's caution about
sequential runs and a warming driver cache applies here too, so what is safe to
say is that **V25.1 does not cost render performance and probably saves a
little** — the triangle count is the number a scheduler should budget from.

## 18. Tests

`tests/test_sloped_v251_world.py` — 38 tests, in five groups:

* **Nothing reached the race.** The seed is 5432, the lab renders V22.1's own
  two solved track files rather than re-solving, the moments and clips are
  V25's own objects (`is`, not `==`), `course_terrain.height`'s body is
  unchanged line for line, and so is layout B's terrain table.
* **Nothing reached the landform.** Neither new module names a collider, a
  physics body or a mesh-shape constructor; `_patches` reads `Terrain.height`
  and writes no terrain state; the profile names no terrain shape field; every
  mesh is on the world light layer and every practical has a world-only cull
  mask; `WorldWarm` is on cull mask 2 with no shadow.
* **V25 still renders V25.** All nine pre-V25.1 profiles are registered,
  resolve and validate, and **none of them sets any of the seven fields that
  switch a builder into its V25.1 behaviour** — which is what makes every V25
  render reproducible from this branch. The dispatcher's fallback path is
  asserted on its source.
* **The kit is a kit.** Eight rock forms and five plants by name, no RNG or
  clock in either module, flat-shaded (`quad_auto` present, `quad_smooth_auto`
  absent), partial ledge arcs, one hero per cluster, every painted surface in
  the palette, every new surface in the marker table, the generator
  regenerating the committed JSON a no-op, and no count above B's.
* **The instruments are sound.** The edit map's values, the projector putting
  four race nodes within a tenth of frame-centre at their own moments, every
  authored site in at least one frame, no site inside a lens, and the analytic
  parallax keeping three bands and a 1.4× spread in three moves.

### V22.1, V23 and V25 B, proved rather than asserted

Three stills — the start grid, the obstacle and the finish — rendered **in one
session** from this branch and from a detached worktree at the base commit
`333703e`, three times: with no `--environment` at all, with V23's
`--environment=aurora_valley --machine=v23b`, and with V25 B's
`--environment=aurora_valley_v25b --machine=v23b`.

    V22.1  at_000.600  at_010.200  at_021.400   BYTE-IDENTICAL
    V23    at_000.600  at_010.200  at_021.400   BYTE-IDENTICAL
    V25 B  at_000.600  at_010.200  at_021.400   BYTE-IDENTICAL

Nine of nine. **In one session** matters and is a finding of this pass: the
same frame rendered from the same tree in two different sessions on this
machine differs by up to 7/255 on 0.44% of pixels, which is screen-space
dithering and driver state, not code. Within a session it is byte-exact. So an
identity proof has to render both sides back to back, and a before-and-after
sheet has to be rendered in one run — which is what `--stage render` does.

### The wider suite

1371 pass. 21 fail and 82 collect with errors, and **every one of those is
`ModuleNotFoundError` for `pybullet` or `pymunk`** — the physics dependencies,
which this worktree does not have and which no file in this pass imports. No
assertion fails, and the count matches what V25 recorded on the same machine.
`tests/test_sloped_v25_world.py`, `tests/test_sloped_v23_*` and
`tests/test_sloped_environment.py` are 517 passed, 1 skipped, unchanged.

## 19. Remaining weaknesses

1. **The midground value tail.** §12. Intrinsic to flat shading, measured, and
   the four things that do not fix it are recorded. The pooled figure is 20.3%
   of world pixels under grey 12 against B's 14.2%.
2. **The distant rock can read as a mosaic.** At the split and the branch,
   twenty-six ridge masses with two buttresses each, all at similar range and
   similar value, make a quilt of angular shapes rather than three or four
   masses. Fewer, larger ridge forms would be the fix and it is a density
   change, which this pass is not allowed to make.
3. **The obstacle has no landmark**, because its camera has no mid-distance to
   put one in (§8). That is a fact about the cut rather than about the world,
   and a reviewer who wants one should ask for a camera change instead.
4. **The `world_ember` zone is the only asymmetric material decision**, and it
   breaks the four-L\* zone rule the other nine follow. It is right for the
   frame it exists for and it is a precedent worth watching.
5. **The bench count is a judgement, not a measurement.** Eleven is where every
   frame has one and no frame has a row; four was too few and fifteen was a
   field. Nothing measures "reads as a foundation", so that number is an eye's.
6. **Scarps are still the weakest near-ground feature.** Three kit `ledge`
   forms per site read far better than five rounded boxes, but at the descent
   they are still the thing most likely to be read as objects rather than as
   strata. They are also the only feature whose sites are authored in plan and
   were not re-derived against the frames.
7. **The image-space parallax test is now half blind on this world** (§15).
   The analytic measure covers it, but a future pass should not read
   `parallax.txt` alone and conclude anything.

## 20. Recommendation

**Ship `aurora_valley_v251` as the world, and watch the full motion proof
before deciding.**

The structural claim of V25 is intact — same cover, same bands, same or better
parallax by the measure that can see this world. The art claim is that the
world is now made of designed forms rather than generated ones, and the
evidence for it is the pair sheets and the clips rather than any number here.

Where it clearly exceeds B: the rock language, the vegetation, the near-ground
material, the removal of the scattered-box problem, the fork's two kinds of
country, the finish basin and its warm ground, and the six frames the east wall
now frames. Where it is a trade rather than a win: the midground is darker and
higher-contrast, and the distant rock is busier.

**It is not ready to combine with V24 on this evidence alone.** The two are
disjoint by construction and the integration is the same two-line change V25
documented — branch from V24's integration, add the two kit modules, the eleven
palette surfaces and the profile, and point the edition at
`aurora_valley_v251`. What has to happen first is the thing the brief asks for
and this document cannot do: somebody watching `full_aurora_valley_v251.mp4`
next to `full_aurora_valley_v25b.mp4` at phone size, twice.

Two things to check when the integration happens, neither of which is a
conflict:

1. **V24's marble markers are saturated, and so is the segmentation.** The
   measurement tooling subtracts the machine by requiring two renders to
   agree, which handles it — but `layer_cover` should be re-measured on V24's
   own frames rather than carried across.
2. **V24 re-cut the film, so the thirteen comparison seconds move.** They are
   output seconds on V22.1's track, and `sloped_v251_sites.replay_second` is
   the function that maps them. Re-derive before re-running any sheet, or the
   sheet will be of the right world at the wrong moments.

V25.1 is **not** merged and is **not** based on V24.
