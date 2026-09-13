# V23 — the environment visual direction lab

**Branch** `v23-environment-direction`, from `origin/main` (e697a12, the accepted
V22.1 Short). **Nothing here is integrated.** The lab is nine new files and zero
edits to any production file; `tests/test_sloped_v23_env.py` checks that against
`origin/main` rather than asserting it.

**Recommended direction: A — Aurora Valley.** Section 9 is the argument.

---

## 1. What this pass was asked

The race presentation is accepted. The next upgrade is the *world* the machine is
installed in: dark background, glowing machine, premium toy presentation,
cyan/blue/violet up high, orange energy where the choice is, gold at the finish,
graphite structure, silver track, atmospheric canyon depth. Three genuinely
different directions, compared on the same frames of the same race, with one
recommended at the end.

Locked, and untouched: physics, seed 5432, route structure, the camera system,
race timing, marbles, country skins, overlays, audio.

## 2. What the V22.1 frame actually does wrong

Three faults, measured rather than felt. `tools/sloped_v23_env.py --stage
measure` prints them for any render, and they are what all three directions were
designed against.

**The sky is the brightest thing in the picture.** Over the eleven comparison
moments the top quarter of a V22.1 frame averages L\* 48.7 with a mean CIELAB
b\* of **+19.7** — a warm tan — while the machine's own 98th percentile is 93.5.
A headroom of 44.8 sounds comfortable and is not: at the fork and the finish the
sky is *lighter* than the pearl track in front of it, and a white machine on a
lighter ground has no silhouette at all. This is the single biggest thing
separating the delivered frame from the concept.

**All the depth investment is below the horizon.** `course_world.gd` builds
three ranges at 210, 380 and 600 units, six lit towers, a warm dusk band and
fourteen haze banks — and almost none of it is ever in a delivered frame:

| what | where it is | where the camera is |
| --- | --- | --- |
| haze banks | y = −96 to −138, radius 430–670 | y ≈ 30, tilted a few degrees down |
| dusk band | y = −78, radius 880 | ~6° **below** the frame's centre line |
| near range | crest at y = +40 | the ground above the start reaches +45 |

The fourteen haze banks and the nine dusk slabs have never appeared in a frame.
The near range is behind the hill it was built to stand behind. The three range
values are within four points of L\* of each other, so even where they do show
they read as one silhouette. `course_world`'s own comment calls the dusk band
"where the light comes from"; it is under the horizon.

**The warm half of the palette is spent on the sky.** The concept's warm accents
are the choice zone and the finish. In V22.1 they compete with a tan horizon
across a third of the frame, and the fork is lit *white* — the one colour that
says nothing about a decision.

## 3. How the lab is built, and why it touches nothing

The environment is authored across `course_world.gd` (sky, atmosphere, ranges,
light rig), `course_terrain.gd` (near ground) and `course_dressing.gd` (lamps,
pylons, valley) — and every one of them is shared with the layout proof, the
hero build, the track lab and the toy lab. Editing them would change four films
to photograph one.

So nothing is edited. `course_env.apply()` runs **after** the production scene
has finished building and re-skins what it finds: the `Environment` resource
field by field, the six named directional lights, the six zone practicals, the
world-only palette materials, the three distant ranges, the haze banks and the
dusk band, plus whatever new atmosphere and landmarks a direction adds under one
`EnvExtras` node. The lab scene is a **subclass** of `sloped_race_scene.gd` and
the lab renderer a subclass of `sloped_race_render.gd`, so the course in frame
is the course that shipped and a lab clip and a production clip are the same
renderer.

`--env=` defaults to empty, which applies nothing at all. A render with no flag
is the V22.1 picture — **verified on pixels, not asserted**. The grid, the
spinner corridor and the finish rendered through `SlopedRaceRender.tscn` and
through the lab's `V23EnvRender.tscn` with no profile hash identically:

```
a8eef740…e61a  at_000.600.png
567f51fc…a94e  at_010.200.png
670fb892…62b6  at_021.400.png
```

`tests/test_sloped_v23_env.py::test_the_lab_renderer_with_no_profile_is_byte_identical_to_production`
re-runs that comparison wherever `$GODOT_BIN` and the generated inputs exist.

**Retinting through the palette cache, and where it stops being safe.**
`lab_palette.get_material` caches one material per key and `lab_forms.mesh_node`
assigns it as a `material_override`, so mutating the cached instance retints
every mesh built from that key and nothing else. `WORLD_KEYS` is the list of keys
that belong to the world alone, and it was checked rather than assumed: three
keys the dressing uses are deliberately **not** on it — `graphite`,
`graphite_deep` and `lit_cyan_line_hero` — because the machine is built from them
too, and retinting `lit_cyan_line_hero` to recolour six pylon beacons would
recolour the start module's edge lighting with them. Those are done as node-level
overrides instead.

## 4. The comparison is fair by construction

Every direction is rendered by one command with exactly one entry changed. Same
solved V22.1 preview and race tracks, same locked `race_5432` replay, same start
contract, same `--finish-sign=double`, same resolution, same detail level, same
routes. Eleven moments, covering every stage the brief lists:

`preview_arena` · `preview_mid` · `preview_start` · `start_grid` ·
`start_release` · `descent` · `obstacle` · `fork` · `branches` · `merge` ·
`finish`

Each race second is inside the cut it is named for on the V22.1 track, so a
still is a frame of that shot rather than a picture near one.

## 5. The three directions

### A — Aurora Valley
*Cold alpine dusk; layered mist; one gold pocket at the finish.*

A deep indigo sky with a cold teal horizon, thickened haze that pools in the
gorge and on every terrace, four steps of cool aerial recession, and the ranges
lifted and stretched until their crests clear the massif. The entire warm half
of the palette is then spent in one place: the finish. The fork practical goes
**orange** — the brief puts warm energy where the decision is, and `split` is the
one node on this course a marble chooses at.

### B — Collector Canyon
*A warm stylised canyon on a cool seamless backdrop; product-lit.*

The direction that deliberately refuses the night. A collector piece is
photographed against a seamless backdrop under a controlled key, so the sky here
is a cyclorama rather than a sky (`sky_curve` three times the others'), the haze
is thin so shapes stay clean, and the glow is the **lowest** of the three because
a lit object is not a lamp. The warm/cool contrast is inverted against Aurora:
cool neutral backdrop, warm putty canyon, and the machine between them as the
only white in the frame. Its ranges are *thinned* — every third mass dropped — so
the backdrop reads as three or four buttes rather than a crowd. Nothing in this
world emits except the machine and a handful of far windows.

### C — Graphite Grid
*A near-black valley the machine is the only light in.*

The brief's third direction taken as far as readability allows. Near-black
graphite ground, a sky close to black, and a short list of environmental lights
that are all the same two colours: thin lit crest lines along the mid ridges and
a sparse cyan grid on the valley floor far below the gorge. What it buys is
silhouette — every edge of the machine has a dark field behind it, which neither
of the other two can promise in every shot.

## 6. What was measured

| direction | headroom | backdrop L\* | backdrop b\* | mean L\* | marble dE | chroma dE | worst clip % | flat backdrops |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V22.1 baseline | 44.8 | 48.7 | **+19.7** | 40.3 | 46.9 | 41.5 | **0.431** | 0/11 |
| A — Aurora Valley | 77.9 | 16.7 | −4.4 | 30.3 | 47.3 | 40.2 | 0.802 | 1/11 |
| B — Collector Canyon | 67.7 | 27.1 | +5.7 | 40.6 | **48.1** | **43.7** | 0.688 | 1/11 |
| C — Graphite Grid | **88.9** | 6.8 | −2.7 | 21.2 | 46.7 | 37.9 | 1.202 | **5/11** |

* **headroom** — the machine's 98th-percentile L\* minus the backdrop band's
  mean. Every direction roughly doubles it; the machine stops competing with its
  own sky.
* **backdrop b\*** — all three move the warmth off the horizon, which is what
  frees the choice zone and the finish to be the warm things in the frame.
* **marble dE** — each racer against the course immediately behind it, borrowed
  unchanged from the V21 contrast pass. **All three now match or beat the
  baseline**, which is the brief's readability constraint met rather than
  traded.
* **worst clip %** — share of the worst frame flat at the top of the range. All
  three sit above the baseline's 0.43 and far under the 5.5% that the V21 pass
  exists to have removed. Graphite is worst at 1.2 and that is inherent: it is
  the direction whose practicals do the lighting.
* **flat backdrops** — moments whose top quarter is a featureless wall. Graphite
  earns 5 of 11, which is the measured form of "the machine is floating in a
  void" and is its main cost.

**There is no layering number in this table, and that is a finding.** Three
measures of "is there depth back there" were built and all three failed, each by
measuring brightness or contrast under another name:

| measure | baseline | A | B | C | why it is wrong |
| --- | ---: | ---: | ---: | ---: | --- |
| σ of L\* in the band | 16.4 | 14.1 | 13.3 | 10.3 | a bright sky with one hard silhouette has a huge range |
| plateau count, absolute L\* | 10.5 | 5.9 | 5.9 | 2.9 | a dark world has few absolute bins to occupy |
| step count in the row profile | 25.7 | 9.0 | 11.5 | 9.0 | dominated by frames with machine in the band — the obstacle frame alone scores 194 steps, none of them sky |

Every one ranks the *problem* above all three of its fixes. The common failure is
that none of them can tell where the backdrop ends: layering is an ordering of
regions by depth, and a single rendered frame does not carry depth. What survives
is the normalised plateau count, kept only for the one thing it does honestly —
**it detects a flat wall**. Depth in this lab is judged on the sheets and the
clips, and the write-up says so instead of pointing at a number.

## 7. Six defects found and fixed, and what each one teaches

**1 — A horizontal mist deck seen from above is a floor, not mist.** The first
gorge mist was six slabs up to 225 units across starting 6 units below the racing
line. Every camera here looks down 15–40°, so they presented almost their whole
area to the lens and came out as a pale sheet with the course sitting on it. Fixed
by pushing them past the gorge lip in +X, dropping the top deck to −28, and
making alpha per-deck and small so the stack accumulates instead of any one deck
reading.

**2 — A lifted haze bank must stop being a lit solid.** `cloud_bank` is a matte
material, which is right for a slab under the horizon contributing a dark value
and wrong the moment it is raised into the sky, where the raking key and the warm
rake both reach it and turn it into a bright painted cloud with a hard rounded
edge. The banks now get an unshaded alpha material with depth-write off.

**3 — Emission survives an albedo alpha of zero.** The first aurora was fifteen
horizontal slabs with `albedo.a = 0` and "faint" emission, on the assumption that
alpha would hold them back. In the unshaded path emission is added after the
alpha the blend uses, so they were fully opaque, and fifteen of them tiled the
upper sky into a solid cyan ceiling with a scalloped edge. Rebuilt as nine tall
narrow curtains spread over 120° of bearing — a ribbon that is mostly gap cannot
become a ceiling however many there are.

**4 — Aerial perspective converges on *the sky*, and these skies are dark.** The
four range values were first stepped toward a light blue-grey, which is the
daylight convention everyone draws from memory: distant hills are paler. They are
paler *because the air between them is lit*. Under a deep indigo dusk the same
physics makes distant rock **darker**, and at the first values the far range came
back a vivid cyan mass floating above the mountain, brighter than the sky it was
supposed to be receding into.

**5 — and the rock albedo was not even the lever.** Correcting the four albedos
barely changed the frame. By 200 units `fog_aerial_perspective` has blended
almost all of the albedo away, so the colour of a distant mass is
`fog_light_color` and nothing else. Blacking all four rock keys out entirely
changed the frame not at all — which is how this was finally found. **The fog
colour is what distance converges to; in a dark world it has to be dark.**
`fog_sky_affect` is raised with it, or a dark haze sits in front of a sky that is
not in it and the horizon goes hard.

**6 — `lift` and `stretch` are not the same lever, and only one of them works.**
The preview's reverse dolly is tilted **up** at the crest above the start; every
race section shot is tilted **down** at the channel. Lifting a range far enough
to reach into a merge frame stands it in the middle of the preview's sky;
lowering it enough to clear the preview's sky takes it out of every race frame.
Three builds each found one end of that and broke the other. `stretch` scales Y
alone about the mass's own origin — which `course_world` has already put on the
range's ground line — so a stretched range appears over the massif's shoulder in
a race frame without rising off the horizon in a preview one.

**A pre-existing V22.1 characteristic, found on the way and not fixed.**
`ProceduralSkyMaterial` draws a halo for *every* `DirectionalLight3D`, and this
scene has six. `course_world` leaves `sun_angle_max` at 46°, so each of the six
paints a halo a quarter of the sky across. It is part of what the V22.1 sky is
and it is invisible under the tan wash; the three directions each set a compact
disc instead. Nothing in production is changed by that.

## 8. Proof outputs

Under `docs/validation/sloped_race_v1/v23_environment/`:

* `contact_sheet.png` — all four directions × all eleven moments, directions as
  rows so a direction can be judged for consistency rather than on a lucky frame
* `sheet_<moment>.png` × 11 — the four directions side by side at one moment
* `phone_sheet.png` — 1170 px wide, the centre 46% of four frames at full
  resolution: the grid (smallest the marbles ever are), the fork (two routes to
  tell apart), the branches (most open air) and the finish (the payoff)
* `measures.json` — every number above, per direction and per moment

Clips, in `output/sloped_race_v1/v23/clips/` (generated output, not in the
branch): `preview_*.mp4`, the whole 3.48 s course preview, and `choice_*.mp4`,
fork through merge — the two spans where a layered backdrop can swim against the
ranges behind it if it is going to.

## 9. Strengths, weaknesses, and the recommendation

| | Aurora Valley | Collector Canyon | Graphite Grid |
| --- | --- | --- | --- |
| readability | strong; dE 47.3, above baseline | **best**; dE 48.1 and the ground stays visible | strong on the machine, weakest chroma (37.9) |
| premium | **strong** — reads as a photographed evening | strong — reads as a product shot | strong but cold |
| toy-like | good | **best**; the warm ground keeps the diorama read | **poor** — reads sci-fi, not toy |
| depth / scale | **best**; four visible steps plus gorge mist | good; fewer, larger buttes | weak — 5 of 11 backdrops are walls |
| memorability | strong; the aurora and the single gold pocket | moderate; closest to conventional | **strongest** single frame, thinnest world |
| machine palette | **exact match** to the concept | its warm ground competes with orange + gold | matches cyan/graphite, loses the warm story |
| V22.1 cameras | no issue | no issue | the down-tilted section shots open onto a void |
| clip discipline | 0.80% | **0.69%** | 1.20% |

**Recommended: A — Aurora Valley.**

The concept the brief describes — dark background, glowing machine, cyan/blue/
violet high in the frame, orange where the choice is, gold at the finish,
graphite structure over a silver track, atmospheric canyon depth — is close to a
literal description of this direction, and the other two each refuse one clause
of it on purpose. Collector refuses the dark background; Graphite refuses
toy-like. Aurora is also the only one that improves depth, readability and the
warm-accent story at the same time: it roughly doubles the headroom, keeps the
marbles' separation above the baseline, moves the warmth off the sky and onto the
fork and the finish, and is the only direction with four visible steps of
distance in the preview frames.

The finish is the clearest single case. In the baseline the FINISH board is gold
on a bright tan sky and barely reads; in Aurora it is gold on near-black with a
violet ridge behind it.

**What to borrow from the other two if this goes forward:**

* from **Collector** — its near-ground value. Collector's canyon stays visible
  in the branch and merge frames where Aurora's goes dark, and world embedding is
  a brief requirement. Aurora's `slope_*` values were already lifted once for
  this and could take one more step.
* from **Collector** — its glow discipline (0.85 / 0.16 / 1.40). Aurora at
  1.10 / 0.22 / 1.30 is why its worst frame clips 0.80% against Collector's 0.69.
* from **Graphite** — the crest lines. They are the cheapest landmark in the lab
  and Aurora has no equivalent at that distance.

**Not recommended: merging any of it yet.** This is a lab; see below.

## 10. Integration notes

The lab was built so that integrating it is a small, reviewable change rather
than a merge of this branch.

1. **The profile is the deliverable, not the plumbing.** If Aurora is accepted,
   the change to production is: fold `AURORA`'s values into `course_world.gd`'s
   `build_environment` and `build_lights` and into `lab_palette`'s world keys, as
   a **named pass** the way `CONTRAST_V21` already is — `contrast == "v23"` — so
   every earlier lab's committed frames keep reproducing byte for byte. That is
   the pattern V21 established and it is the only safe one here.
2. **Three fixes are worth taking whatever direction wins**, because they are
   corrections to V22.1 rather than to its colour: the haze banks and the dusk
   band are below the horizon and have never been in a frame; the three range
   values are within four points of L\* of each other; the fork practical is
   white. None of them depends on the sky being dark.
3. **`stretch` has no production equivalent.** Raising the range crests into the
   race frames needs either the Y-scale lever this lab added or taller entries in
   `NEAR_RANGE` / `MID_RANGE` / `FAR_RANGE`. The second is cleaner in production.
4. **Re-solve nothing.** No camera, replay, edit or timing is involved, so the
   V22.1 tracks and the locked replay carry straight over. The only re-render is
   pixels.
5. **Re-run the V21 gate after integration.** `tools/sloped_contrast_measure.py`
   is the project's clip and separation check, and every direction here runs
   above the baseline's clip share. That is fine in a lab and should be measured
   again on a production build.
6. **The `sun_angle_max` finding is independent** and can be taken or left; it
   changes the V22.1 sky, so it belongs in whatever pass changes the sky anyway.

## 11. Running it

```bash
# prerequisites: the locked replay in output/sloped_race_v1/, and
python tools/sloped_v22.py --edition v221 --stage solve
python tools/sloped_v22.py --edition v221 --stage freeze

python tools/sloped_v23_env.py --stage all  --godot "$GODOT_BIN"
python tools/sloped_v23_env.py --stage clip --godot "$GODOT_BIN"
python -m pytest tests/test_sloped_v23_env.py -q
```

A single direction, for iterating: `--only aurora`. A single clip: `--clips
choice`.
