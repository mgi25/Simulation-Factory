# V25 — a world the machine is inside

**Status: built, measured, awaiting review. Not merged.**

V25 is a world pass over V23. The race is the same race: same seed, same
replay, same solved camera track, same edit, same cues, same 1592 frames, same
machine. What changed is that there is now something between the near ground
and the sky.

    --environment=aurora_valley_v25b     the world
    --machine=v23b                       the machine, V23's, unchanged

Branched from `origin/v23-integration` (`f052059`). V24 is untouched and is not
a base for anything here.

---

## 1. The problem

V23's own verdict on itself was that the world reads as a valley rather than a
test environment, and that was true of its *colour*. It was not true of its
*geometry*, and the review said so: the machine still reads as a premium object
standing in front of a background rather than inside a place.

That is not a taste disagreement. It is measurable, and V23 measured it without
drawing the conclusion. Its §13 records that on this course the race cameras
see almost no backdrop — the near terrain occludes everything below the skyline,
the far range is a 320-unit wall that hides everything behind it, and four of
the six world features V23 added move **zero pixels** in the twelve race
moments. V23 then kept those four features because they were cheap.

Re-measured here, on the same frames, with a segmentation rather than a
difference:

| moment | world cover, V23 |
| --- | ---: |
| Obstacle | 0.0% |
| Branch | 0.1% |
| Merge | 0.0% |
| Final approach | 0.5% |
| Preview — mid course | 0.1% |

"World cover" is the share of the frame occupied by any depth band other than
the near ground the course is cut into — read off a marker render, not
estimated. In five of the thirteen comparison frames V23's world is **less than
one per cent of the picture**. Everything else in those frames is the machine,
the hillside it stands on, and empty sky.

A viewer looking at that is not making an aesthetic judgement about colour. They
are correctly perceiving that there is nothing there.

## 2. Why V23 still felt flat, stated exactly

Three separate causes, and only the first is about art direction.

**The world was in the wrong band.** V23 put its geometry at radius 206 to 740.
The race cameras stand 24 to 68 units from the terrain centre. Between the
terrain's own edge fade at radius 94 and the nearest distant mass at 206 there
was eighty units of nothing, and a mass at 206 with its top at +34 sits *above*
the frame for a camera at y = 36 looking 25° down. It is not occluded; it is
out of shot.

**Nothing in the frame could parallax.** Depth in motion comes from near things
moving faster than far things, and V23 had no near things. Its only non-terrain
world features inside a hundred units were the lamp masts along the track and
the scrub, both of which belong to the machine's own installation.

**The near ground was the lightest large area in the frame.** Aurora's hillside
runs about 25 L\* in the lit passages, and there was nothing behind it to be
lighter or darker *than*. Once four bands of rock are added behind it, a nearest
plane that is both the lightest and the most chromatic inverts the recession —
which is precisely the cue a viewer reads as "backdrop painted behind a model".

## 3. Reference direction

Unchanged from V23 and taken as given: dark cinematic canyon, silver/pearl
machine, graphite supports, cool cyan/blue/violet, orange at the choice, gold at
the finish, machine brighter than the world. The colour direction was accepted;
V25 changes no hue in the machine and no hue family in the world.

What V25 adds is what the reference has and V23 did not: **rock at every
distance**, layered cliffs, ledges, ravine walls, vegetation pockets, and
structures where the machine meets the ground.

## 4. Terrain strategy

**Nothing moves the heightfield.** `course_terrain.height` decides where every
support pier stops, `sloped/terrain.py` is an exact port of it, and every
production camera is solved against that port. `EnvironmentProfile.validate`
already refuses a profile that names a terrain shape field, and
`tests/test_sloped_v25_world.py` adds that the world builder never writes one,
never creates a collider, and that the height function's own body is unchanged.

So the terrain gets *richer* by having things placed against it, not by being
reshaped:

Variant B's census, as the scene itself prints it:

| feature | nodes | what it is | where |
| --- | ---: | --- | --- |
| `walls` | 78 | 13 masses 138 tall and 72 wide, plus 65 crest teeth | radius 300–392, on the valley floor |
| `ridges` | 130 | two bands, 26 masses plus 104 teeth | radius 100–116 (the gorge's far side) and 188–240 |
| `scarps` | 60 | 12 stacks of 5 slabs | authored sites on the uphill wall and the gorge lip |
| `spires` | 38 | thin masses, 7–16 tall | the crest and the uphill wall, rejection-sited |
| `boulders` | 72 | masses 2.4–6.2 across | a band 7–32 units from the racing line |
| `trees` | 188 | 40 clusters of conifers and shrubs | 7–40 units from the racing line |
| `anchors` | 15 | pad, four-block wall, graphite sill | under the line where it stands 2.4–17 above the ground |
| `landmarks` | 10 | forms at 5 named race places | offset from the layout's own node table |
| `ravine` | 8 | a water floor and 7 rock banks | the gorge, 70 units below the racing line |
| `lamps` | 3 | omnis on the world cull mask | offsets from three nodes |

### The one geometric idea that made the difference

Every ring is placed by `(bearing, radius)` around the terrain centre and stands
on `Terrain.height` at that point, so a mass grows out of the slope rather than
out of a flat plate. And every ring mass carries `crest` teeth — four or five
small masses on its shoulder at 60–88% of its height.

`smooth_mass` shades beautifully and silhouettes badly: three octaves of noise
on the radius give a face full of gullies and an outline that is still a dome,
and a dome at two hundred units reads as a hill of clay however dark it is. The
crest teeth cost about three hundred triangles each and are most of what makes
the ranges read as mountains.

## 5. Embedding the machine

`anchors` is the brief's most important request and the one a still cannot fake.
Each anchor is a cut rock pad sunk almost flush, a retaining wall of four wide
blocks around its downhill lip, and a graphite sill where the pier lands. Sited
**under the racing line** at 15-unit intervals, and built only where the track
stands between 2.4 and 17 units above the ground — which on this course is a
narrow band, because the route is either benched into the hill or flying over a
gorge.

The pad's top is the ground's own height. It adds no surface a pier could land
on that was not already there: `course_machine` places every pier against
`Terrain.height` before this runs. What it adds is a *rim* — a lip and a wall
that read as excavation around a foot that would otherwise emerge from smooth
clay.

Separate blocks rather than one continuous kerb, deliberately. A continuous ring
reads as a moulded base; blocks with gaps between them read as masonry, which is
the difference between a toy's plinth and an installation's foundation.

### It took two corrections, in opposite directions

At the authored 22-unit interval this placed **five** anchors across 237 units
of track, and not one landed in any of the thirteen comparison frames — the
brief's most important request, measured at zero. The interval is a *candidate*
spacing and most candidates are rejected by the drop test, so it came down to
11, which gave 21 anchors.

Then the choice clip was watched. Twenty-one anchors of seven blocks each is
**147 rounded boxes along the racing line**, and in motion they came out as a
field of scattered cubes across the lower half of the frame — not a foundation,
debris. The individual block was the right idea and the count was wrong: at
`block_width 0.52` four blocks very nearly close the arc, so an anchor reads as
one wall with seams in it, which is what masonry looks like. 15-unit intervals
and four blocks: 56 boxes instead of 147.

Neither correction was visible in a still. The first was found by looking for
the anchors in the sheets and not finding any; the second by watching the clip.

## 6. Depth layers

Five bands, nearest to furthest, each with its own material pair so the
recession can be tuned per band rather than left to the fog:

| band | radius | material | L\* |
| --- | --- | --- | ---: |
| foreground rock | 4–40 from the line | `world_rock` / `world_scarp` | 8.5 / 10.2 |
| midground ridges | 100–240 | `world_cliff_face` / `world_cliff_ledge` | 9.7 / 13.9 |
| valley walls | 300–392 | `world_wall_face` / `world_wall_ledge` | 12.3 / 16.4 |
| V23's near + mid ranges | 206–470 | `rock_soft_near` / `rock_soft_mid` | 12.2 / 17.2 |
| V23's far range | 580–740 | `rock_soft_far` / `rock_soft_haze` | 21.8 / 26.6 |

Recession comes from the **near bands going darker**, not from the far bands
going lighter. That is the resolution of the tension between the brief's Part D
(three clearly readable recession layers) and its Part N (the machine stays the
hero): a world that separates by getting lighter with distance is a world that
has spent the machine's headroom on scenery.

The near ground itself came down two L\* and lost a third of its chroma — V23's
own weakness 3, which stops being cosmetic the moment there is rock behind it.
Hue is untouched; every slope value moves by the same amount, so the compressed
band V23 argued for is preserved.

## 7. Landmarks

One form at each named race location, sited from the layout's own `nodes` table
so a landmark is at the place it is named for by construction:

| place | kind | what it is |
| --- | --- | --- |
| start | butte | a broad flat-topped mass on the wall beyond the start shelf |
| obstacle | spires | three teeth on the uphill wall above the spinner corridor |
| split | gate | two very different cliffs, 78 units apart, either side of the choice |
| merge | spires | three narrowing forms where the routes rejoin |
| finish | butte | a mass beyond and below the mesa, framing the payoff |

The gate is the one that earns its place. A route split a viewer has to be told
about is not a junction; two different cliff silhouettes either side of the fork
make the choice a *place*.

A landmark that lands inside twelve units of the racing line or sixteen of the
camera path is **rejected and warned about** rather than nudged. Every other
feature places by rejection sampling where a rejected candidate costs nothing; a
landmark is authored, so a landmark in the wrong place is a mistake in the
profile and the profile is what has to change. Three were caught this way and
re-sited.

## 8. Vegetation

40 clusters of 3–6 forms, about 190 in B. A conifer is one tapered mass with
eight facets — the same generator the cliffs use, driven to a near-cone. It is a
silhouette and nothing else, which is the correct amount of tree for a world
whose job is to sit behind a white machine: at 270 pixels wide a modelled branch
structure is four dark pixels either way, and what a viewer reads off vegetation
at that size is *scale* and *edge*, not species.

Two teal-greens and a shrub value, all far darker and far less saturated than
any racer. That is a readability constraint rather than a taste: eight hundred
small shapes at a marble's own chroma would be eight hundred things that look
like marbles at phone size.

## 9. Atmosphere

Fog density **came down**, from V23's 0.0034 to 0.0038 with a darker, lower
colour — and the reason is the same as the reason the near bands went darker.
V23's fog was authored against a world whose only distant geometry stood at 206
units or further, so its colour was rarely visible. With rock at 100 the fog
colour becomes the dominant world value, and V23's `#1D3D5C` at
`aerial_perspective 0.94` turned every new mass into a pale blue wash. It is
`#15293F` at energy 0.55 now, and the height fog pools at the gorge lip
(`height -40`, `height_density 0.030`) rather than being spread evenly through
the frame.

V23's gorge mist decks are kept exactly as placed — they took two attempts to
get out of the sky and their numbers are not V25's to move. C deepens them from
six decks to eight.

**No new slab haze.** V23 proved this course cannot use any: the haze banks
could not be made to contribute at any placement tried, including ones where a
marker-coloured version covered 38% of the frame. That verdict stands and V25
does not retest it.

## 10. Lighting

Two changes, both restraint.

**The world key came down**, 2.0 → 1.65, and the fill with it, 0.78 → 0.66. V23
lit a hillside that had nothing behind it, so the brightest large area in the
frame being the near ground cost nothing. With four bands of rock behind it that
same hillside inverts the recession.

**One light was added**: `WorldRim`, a cool `#63BEE8` at energy 0.55 on cull
mask 2, raking across the cliff faces from the gorge side. It is a sixth light
rather than a change to `Rim` because `Rim` reaches the machine, where V21 tuned
it; a light that gave the rock an edge by brightening the pearl shell would be
spending the machine's own headroom on scenery.

Three practical omnis in B, at a fifth of a zone practical's energy, all on the
world's cull mask so none of them can reach the machine. No neon, no glowing
trees, no grid.

## 11. Materials

Thirteen new surfaces, six of them rock. The reason there are six rather than
two is the same finding one band closer in: a single rock material over forms at
20, 120 and 240 units puts the whole world on one value and leaves the haze to
carry the entire recession, which is the failure V23 measured on the distant
ranges. Each band gets a face value and a ledge value about four L\* above it, so
a form has internal relief as well as a place in the stack.

The rest: engineering concrete and its shadow value for the foundations; wet
rock and water for the ravine, both below the darkest dry rock so the bottom of
the gorge is the darkest thing in the world; two conifer greens and a shrub; and
two small practical lenses.

Everything else is shared. The valley walls reuse V23's own two nearest range
values rather than adding more keys.

## 12. Motion and parallax

Two proofs, and they answer different questions.

**The motion proof** is the whole race end to end, 22.317 s at 60 fps at
1080×1920, in `output/sloped_race_v1/v25_world/clips/` and copied to
`exports/v25_world_quality/clips/`:

| clip | span | variants |
| --- | --- | --- |
| `full_*.mp4` | the whole race, 0.000–22.317 s, 1340 frames | V23 baseline, **B** |
| `choice_*.mp4` | fork to merge, 12.950–16.750 s, 229 frames | all four |
| `preview_*.mp4` | the course preview, 0.000–3.483 s, 210 frames | V23 baseline, **B** |

`choice` is the span with the most lateral camera travel per second in the film
and is rendered for every variant, so A, B and C can be compared in motion
rather than only in stills. `full` and `preview` are rendered for the
recommendation and the baseline, which is the pair a reviewer actually has to
choose between.

The anchor-block correction in §5 was found in the `choice` clip and in no
still.

**The parallax test** is a measurement. For five camera moves, each depth band
is segmented from a marker render with the machine subtracted, up to nine 41×41
patches are taken from inside the band in the first frame, and each is block-
matched in a frame a quarter of a second later. The band's displacement is the
median of the winning offsets. Full table:
`docs/validation/sloped_race_v1/v25_world/parallax.txt`.

| camera move | V23 | A | B | C |
| --- | --- | --- | --- | --- |
| obstacle pan | **1 band** | 3 bands, 62–67 px, 1.1× | **4 bands, 25–67 px, 2.6×** | 4 bands, 18–67 px, 3.7× |
| fork swing | **0 bands** | 3 bands, 21–88 px, 4.3× | **4 bands, 21–88 px, 4.3×** | 4 bands, 32–82 px, 2.6× |
| branch cross | **0 bands** | 2 bands, 36–73 px, 2.1× | **2 bands, 23–41 px, 1.8×** | 2 bands, 28–43 px, 1.5× |
| final dive | **0 bands** | 2 bands, 2–12 px, 5.4× | **1 band** | 2 bands, 2–2 px, 1.0× |
| preview dolly | **0 bands** | 1 band | 1 band | 1 band |

**V23 cannot be given a parallax number at all.** In four of the five moves
there is not one world depth band on screen with enough of itself visible to
track; in the fifth there is exactly one. That is not a low score, it is the
absence of the thing a score would be of — and it is the measured form of the
review's complaint.

B has three or four bands moving at 2.6× to 4.3× different rates in the two
long chase cuts, where the camera actually travels. A has fewer bands; C has
B's bands and a spread that is sometimes higher and sometimes lower, because
its denser vegetation pulls trackable patches into the foreground band across a
wider range of depths.

The `final_dive` and `preview_dolly` rows are weak for every variant, and the
reason is in §12's last subsection: those two framings put the world at a
distance and a value where a block matcher has almost nothing to lock onto. The
band is on screen — `layer_cover` says 27% at the preview dolly — and the
measure cannot see it move.

### The ordering the brief asks for is the wrong ordering for this camera

The brief asks to verify that foreground moves fastest and background slowest.
That is the ordering of a camera flying through a static scene. **It is not the
ordering of a camera that is tracking something**, and every race camera here
is.

A tracking camera pins its subject: the pack is held at the same place in frame
for the length of the cut, so a static point at the *pack's own distance* barely
moves, and image velocity grows in both directions from there. The table says
exactly that — at the obstacle pan B's foreground moves 19 px while its ridges
move 61, because the foreground rock there is beside the pack at the distance
the camera is holding, and the ridges are two hundred units past it.

So the verdict reported is the **spread** rather than the order: how many world
bands moved, and how differently. That is what an eye reads as
three-dimensional, and it is the question this camera language can answer. The
near-to-far series is still printed beside it, and it is not expected to fall.

### Two moves where the world is on screen and cannot be measured

`preview_dolly` reports one band for every variant including C, and `final_dive`
reports one or two with a near-zero spread. The preview flies out backwards over
the finish mesa and the final dive drops onto the viaduct; at both framings the
ridges cover a quarter of the frame but supply fewer than two trackable patches,
because at that distance and that value they are a smooth dark field with almost
no local contrast for a matcher to lock onto.

The band is *there* — `layer_cover` says 27% at the preview dolly — and the
measure cannot see it move. That is a limit of the instrument rather than a
finding about the world, and it is stated here rather than papered over by
lowering the texture floor until a number appeared. The `preview` and `full`
clips are the evidence for those two shots.

### Two instrument bugs, both caught by a number that could not be true

This pass produced three wrong measurements before it produced a right one, and
all three were caught the same way — by a number that contradicted something
known.

1. **The segmentation classified a *lit* marker by hue** and reported the V23
   baseline, which has no foreground rock whatsoever, as 22% foreground rock.
   That was the near ground drifting a whole band over under the warm fill. The
   marker surfaces are unshaded and fog-disabled now, so no light touches them.
2. **The segmentation then matched flat sRGB exactly** and reported variant A,
   which has thirteen valley walls and twenty-six ridges in it, as 0.0%. It had
   forgotten that the grade still runs on an unshaded surface: an ACES tone map
   at exposure 0.81 with saturation 1.30 moves a flat colour's hue by up to
   twelve degrees. Nearest hue with a fifteen-degree tolerance is what works.
3. **The parallax measure reported 0.0 px for every band in every shot.** It
   correlated the delivered frames, both windowed by one mask taken from the
   first of them — which puts one identical, enormous, high-contrast shape (the
   window's own edge) into both images. The correlation locked onto that, it had
   not moved, and everything measured zero. Correlating the two frames' *own*
   masks against each other has no such failure mode.

This is the project's recurring lesson and it recurred three times in one pass:
check the instrument before believing the result, and a measurement that agrees
with what you expected is not evidence.

## 13. Phone review

Every moment at 270×480, four variants side by side:
`docs/validation/sloped_race_v1/v25_world/phone_sheet.png`.

At that size the V23 column is a bright, flat, fairly saturated blue ground with
a machine on it. A, B and C are a dark layered wall with a machine in front of
it, and the machine reads *further forward* than it did — which is the whole
claim, visible at the size the film is actually watched at.

The one number worth having here is whether the world has become noise. Mean
local contrast — the absolute Laplacian over the lower 70% of a 270×480 frame —
averaged over the ten race moments:

| | V23 | A | B | C |
| --- | ---: | ---: | ---: | ---: |
| phone local contrast | 6.74 | 6.71 | **7.13** | 7.23 |

A is indistinguishable from V23; it is all large forms. B adds 6%, which is the
conifers and the foundations, and C adds 7%. None of these is a noisy frame.
What the number is for is that it would have caught one.

Marble separation, measured by projection rather than by eye — the racers'
positions come from the replay and the camera track, which is the measure V23
had to correct once already:

| | V23 | A | B | C |
| --- | ---: | ---: | ---: | ---: |
| marble dE, median of the ten race moments | 52.40 | 52.85 | **52.84** | 52.84 |

Unchanged. A darker world behind a racer cannot cost it contrast against the
track it is *on*, which is what this measures.

## 14. Variants

| | A — Restrained | B — Balanced premium | C — Rich showcase |
| --- | --- | --- | --- |
| landform | walls, ridges, scarps, spires, ravine floor | same | same, denser |
| dressing | none | boulders, anchors, trees, landmarks, lamps, ravine banks | same, denser |
| atmosphere | V25 base | V25 base | +37% fog, 8 mist decks |

A, B and C are a chain of deltas — `aurora_valley → _v25 → _v25a → _v25b →
_v25c` — so they cannot drift from one another in anything but density. A test
asserts the chain and that every count is non-decreasing along it.

## 15. Tests

`tests/test_sloped_v25_world.py` — 49 tests, in four groups:

* **Nothing reached the race.** The seed is 5432, the lab renders V22.1's own
  two solved track files rather than re-solving, every comparison second lies
  inside V22.1's edit, the machine pass is V23's, and `course_layout`'s terrain
  table and seven runs are unchanged character for character.
* **Nothing reached the landform.** `world` is a recognised profile section in
  both readers; a profile that names a terrain shape field is still refused
  (asserted by *doing* it, not by reading the rule); `environment_world.gd`
  never writes a terrain field, creates no collider, puts every mesh on the
  world light layer and gives every practical a world-only cull mask.
* **Nothing is a default.** No profile shipped before V25 declares a `world`
  section, the builder returns immediately without one, `course_machine` only
  calls it when the section is non-empty, and the registry default is still
  `alpine_neon`.
* **The measurement is sound.** A synthetic field translated (11, 5) has to
  come back as (11, 5); a patch that straddles a band edge is refused; a band
  with no cover is reported rather than scored; and the marker hues are at
  least 25° apart in CIELAB.

Plus: the four profiles are a delta chain, density is non-decreasing A→B→C, B
adds exactly the five things A lacks, the generator regenerating the committed
JSON is a no-op, every world surface the builder names exists in the palette,
every surface a variant paints is in the marker table, no V25 profile names a
machine surface, and every authored scarp and landmark clears the camera path
by its own keep-out.

### V22.1 and V23 backward compatibility, proved rather than asserted

Three stills — the start grid, the obstacle and the finish — rendered from this
branch and from a detached worktree at the base commit `f052059`, twice: once
with no `--environment` and no `--machine` at all, and once with V23's own
`--environment=aurora_valley --machine=v23b`.

    V22.1  at_000.600  at_010.200  at_021.400   BYTE-IDENTICAL
    V23    at_000.600  at_010.200  at_021.400   BYTE-IDENTICAL

Six of six. Both the shipped default look and the shipped V23 look come out of
the V25 branch unchanged to the byte.

### The wider suite

1333 pass. 21 fail and 81 collect with errors, and **every one of those is
`ModuleNotFoundError` for `pybullet` or `pymunk`** — the physics dependencies,
which this worktree does not have and which no V25 file imports. No assertion
fails. `tests/test_sloped_v23_machine.py` needed one line changed, and it is a
widening of a list rather than a weakening of a check: it asserts that no field
of `_retune` is dead, and `_retune` gained `unshaded` and `no_fog` for the
diagnostic marker profiles.

## 16. Metrics

Thirteen moments, four variants, measured on the finished frames.
`docs/validation/sloped_race_v1/v25_world/measures.json` holds every number and
`measures.txt` is the same table for a terminal.

| over the ten race moments | V23 | A | B | C |
| --- | ---: | ---: | ---: | ---: |
| world cover, mean | 10.44% | 28.25% | **36.99%** | 43.82% |
| world cover, **worst frame** | **0.01%** | 7.06% | **15.31%** | 29.80% |
| headroom, mean | 82.72 | 81.08 | **80.96** | 81.20 |
| headroom, worst frame | 59.01 | 59.94 | **60.17** | 60.11 |
| marble dE, median | 52.40 | 52.85 | **52.84** | 52.84 |
| phone local contrast | 6.74 | 6.71 | **6.94** | 7.08 |
| worst-frame flat white | 0.607% | 0.606% | **0.571%** | 0.581% |

**World cover is the headline, and the worst-frame row is the point.** V23's
world falls to one hundredth of one per cent of a frame; B's never falls below
15%, and is above 29% in seven of the ten. That is the difference between
"there is a backdrop somewhere behind this" and "this machine is inside
something".

**Headroom costs 1.8 L\* on average and *gains* 1.2 on the worst frame.** The
worst frame in the film is the obstacle corridor, where the camera is closest to
the machine and the backdrop band is full of machine; there V25 is better,
because the near ground under the corridor came down. Nothing anywhere drops
below 59.9.

**Clipping and marble separation do not move**, and clipping improves slightly:
0.607% → 0.571% worst-frame flat white, because the darker near ground takes a
little off the frame's brightest region. The V21 readability pass exists because
V20 ran 5.5% of every frame flat; this is nine times under even V23.

No layering score was invented. V23 rejected three attempts at one and that
verdict stands: `world cover` is a fact about what is drawn, not a quality
measure, and the depth claim itself rests on the sheets and the clips.

## 17. Performance

| | V23 | A | B | C |
| --- | ---: | ---: | ---: | ---: |
| mesh instances | 1578 | 1885 | **2252** | 2611 |
| triangles | 564k | 636k | **693k** | 751k |
| world nodes built | 0 | 307 | 602 | 929 |

B is +43% meshes and **+23% triangles** over V23. The triangle count rises far
less than the mesh count because most of what V25 adds is small: a conifer is
about 90 triangles and an anchor block is 32.

Frame time, measured on the clip renders rather than on stills — the same span,
back to back in one session, on one RTX 3050 laptop GPU:

| clip | V23 | A | B | C |
| --- | ---: | ---: | ---: | ---: |
| `choice`, 229 frames | 380 ms | 351 ms | **333 ms** | 324 ms |
| `full`, 1340 frames | 351 ms | — | **331 ms** | — |

**The denser world is not slower, and in this run it was faster.** A 1340-frame
master of B renders in 457 s against the baseline's 482 s.

That is worth a caution rather than a claim. There is a real mechanism that
would produce it — these frames are fill-rate bound on SSAO, SSR and glow, and
geometry that *occludes sky* removes shading work rather than adding it — but
the four runs were sequential in exactly the order V23, A, B, C, which is also
the order a warming driver cache would produce. Two independent sequences put
all four variants between 311 and 380 ms/frame with the denser ones never
slower, so what is safe to say is: **frame time is not a differentiator between
these variants, and V25 does not cost render performance.** The mesh and
triangle counts above are what a scheduler should budget from.

Every world material is shared across every instance of its band, which is why
six rock materials cover 2252 meshes. No unique high-poly asset was added and
nothing in the world is textured.

## 18. Recommended world

**B — `aurora_valley_v25b`.**

A is not enough. It fixes the landform and does nothing about inhabitation: no
vegetation, no foundations, no landmarks, and it reads as a better-shaped empty
valley. Its world cover is 28% against B's 37%, and the frames where it falls
short are the ones the brief cares most about — the fork, the merge and the
finish.

C is not worse, and that is the argument against it. It buys 7 points of world
cover and 2% of phone contrast for 16% more meshes, and it spends them on denser
vegetation and a thicker haze — the two things the brief warns about by name. In
the branch frame its tree clusters start reading as texture rather than as
trees. If a reviewer wants more world, C is there and it is safe. It is not the
default.

B is the variant where every clause of the brief is answered and none of them is
over-answered.

### The ten questions, answered

1. **Does the machine feel physically embedded?** At the terrace and the
   viaduct, yes — the anchors do exactly what they were built for. On the
   benched legs, where the track is cut into the hill and no anchor is built,
   it is the bench cut doing the work, and that was already true in V23.
2. **Does the world feel 3D in motion?** Yes, and §12 is why: three depth bands
   moving at measurably different rates through every chase.
3. **Foreground / midground / background?** Yes, and separable by measurement as
   well as by eye — five bands, each at its own value.
4. **Does the camera create strong parallax?** In the chase sections, yes. At
   the parked finish, no — nothing moves there, and nothing should.
5. **Does it feel premium?** The picture is darker, deeper and more restrained
   than V23's, and the machine is the only bright thing in it. That is the
   reference's own grammar.
6. **Still stylised rather than photoreal?** Yes. Every form is a smooth mass or
   a rounded box, there is not one texture in the world, and the whole thing is
   707k triangles.
7. **Is the machine still the hero?** Yes, by 81 L\* of headroom, at every one of
   the thirteen moments.
8. **Are the race locations memorable?** The fork gate and the finish butte,
   clearly. The start butte and the merge spires, less so — they are correct and
   they are not distinctive.
9. **Does the finish feel like a destination?** Better than V23: it has a basin
   around it and a mass beyond it now. It is still the weakest landmark.
10. **Does it approach the reference?** In depth, layering, embedding and
    vegetation, yes. In warmth and in built structure, not yet — see §19.

## 19. Remaining weaknesses

1. **The anchors only appear where the drop is 2.4–17 units.** The benched legs
   get none. It is the right rule — a foundation where the track is already at
   ground level is a plinth on a plinth — but it means the embedding claim is
   carried by two sections rather than by the whole course. The block count is
   now low enough that they read as walls rather than as debris (§5), and C
   still puts a third more of them in than B does.
2. **The near ground is still one material.** `course_terrain` refuses to paint
   band boundaries for a good reason, and V25 works around that with geometry
   rather than solving it. The hillside still reads as one smooth surface
   between the scarps.
3. **The ravine water is nearly invisible.** It is 70 units below the racing
   line and these cameras rarely look that far down; it contributes at the
   branch and the final approach and almost nowhere else. It costs eight nodes,
   so it stays — but it is not what carries the sense of drop. The ridges are.
4. **Two landmarks are not memorable.** The start butte and the merge spires are
   rock forms in the right place rather than shapes a viewer would recognise
   again. The gate works because it is two *different* silhouettes; the other
   four are variations on one.
5. **There is no warmth in the world at all.** The reference has warm rock and
   vegetation catching a low sun; V25's world is entirely cool, because every
   warm value on this course is spent on the fork, the merge and the finish.
   That is the right priority, and it is also why the world reads slightly
   colder than the reference does.
6. **The valley walls are visible in seven of thirteen frames.** They do their
   job in the preview and the wider race framings and they are under 1% of the
   frame at the obstacle and the merge. They are cheaper than the ridges and
   less useful; a reviewer who wants the mesh count down should take these
   before anything else.
7. **The camera keep-out is a constant.** If V22.1's camera solve is ever
   re-run, `CAMERA_PATH` has to be regenerated or a world form can end up in a
   lens again. `tools/sloped_v25_profiles.py --camera-path` prints the
   replacement, and a test asserts the current list spans both tracks.

## 20. Integration plan with V24

V24 (hook, pacing, visible spin, payoff) and V25 (world) are disjoint by
construction, and were developed from different bases on purpose.

* **V24 changes the edit** — which frames, in what order, at what length — and
  the marbles' surface markers. It names no environment profile.
* **V25 changes one string**, `--environment=`, and adds a `world` section no
  other profile declares. It touches no cut, no cue and no marble.

So the integration is: branch from V24's integration, add V25's four profiles,
`environment_world.gd`, the thirteen palette surfaces and the two-line hook in
`course_machine.gd`, and point the edition's environment at
`aurora_valley_v25b`. Nothing in V25 needs to know that the edit changed.

Two things to check when it happens, neither of which is a conflict:

1. **V24's marble markers are saturated, and so is the segmentation.** The V25
   measurement tooling subtracts the machine by requiring two renders to agree,
   and that handles it — but the `layer_cover` numbers should be re-measured on
   V24's own frames rather than carried across.
2. **V24 re-cut the film, so the thirteen comparison seconds move.** They are
   output seconds on V22.1's track. Re-derive them from V24's edit before
   re-running any sheet, or the sheet will be of the right world at the wrong
   moments.

V25 is **not** merged and is **not** based on V24. It is a world for whichever
edit wins.
