# V23 — the environment system

**Branch** `v23-environment-system`, from `origin/main` at `e697a12`.
**Status** framework, awaiting review. Nothing is merged and nothing about the
shipped picture changes.

V22.1's camera looks further ahead than any camera before it and puts far more
world in frame, so the environment stops being backdrop and starts being
content. This branch does not answer *what that content should look like*. It
answers **where the answer goes**, so that the next several answers — a canyon
map, a glow valley, a second course — are files rather than branches.

---

## The problem it solves

Before this branch the world was six sets of constants in four scripts:

| what | where it lived |
| --- | --- |
| sky, fog, grade, glow, the six-light rig, three mountain ranges, the lit structures, the horizon band, the cloud banks | `course_world.gd` |
| the four ground material keys, the boulder values | `course_terrain.gd` |
| lamp masts, scrub, ridge pylons, valley lights, the course spill | `course_dressing.gd` |
| the practical at each race moment | `course_scene.gd` |

Changing the art direction meant editing four files. *Keeping two directions*
meant branching them, and a branched look cannot be compared against the one it
came from without two checkouts and two renders.

An `EnvironmentProfile` is that same set of numbers as data, in one JSON file,
under one id. One flag selects it:

```
--environment=canyon_dusk
```

---

## Architecture

```
godot/assets/marble_machine/environment/
    environment_profile.gd      load, inherit, overlay, validate  (GDScript reader)
    environment_builder.gd      a resolved profile -> scene nodes, lights, env
    profiles/
        index.json              the registry and its default
        alpine_neon.json        the root: the shipped V20/V21 look, complete
        canyon_dusk.json        a delta
        glow_valley.json        a delta
        mono_readability.json   a delta
sloped/environment.py           the same JSON, read from Python
tools/sloped_environment.py     list / check / show / diff / sheet / measure / neutral
tests/test_sloped_environment.py
```

Data flows one way:

```
profiles/*.json
   |  environment_profile.resolve(id, contrast)      <- inheritance, overlay, accent
   v
resolved profile (one dictionary)
   |
   +-> environment_builder.environment()    -> WorldEnvironment
   +-> environment_builder.lights()         -> the six-light rig
   +-> environment_builder.backdrop()       -> ranges, landmarks, band, clouds
   +-> environment_builder.apply_palette()  -> surface overrides on lab_palette
   +-> environment_builder.terrain()        -> ground material keys + scatter passes
   +-> environment_builder.dressing()       -> lamps, scrub, pylons, valley, spill
   +-> environment_builder.zone_lamps()     -> the practical at each race moment
```

`course_world.gd` is now a sixty-line seam that resolves a profile and
delegates. It keeps its old signatures, because four scenes and a dozen proof
tools reach the world through them and a profile system whose first act is to
break every caller is not a framework.

### Two readers, one source of truth

The profiles are JSON rather than GDScript dictionaries for one reason: so
`environment_profile.gd` and `sloped/environment.py` can parse the *same bytes*
instead of transcribing them at each other. A Python mirror of a GDScript table
is an instrument bug with a schedule — this project has paid for that class of
bug twice, and the memory of it is why the numbers live in neither language.

What can still drift is the *logic* — the section list, the shape-field list,
the merge rule — so `tests/test_sloped_environment.py` reads the GDScript as
text and compares its constants with Python's.

---

## The rules

### 1. GEOMETRY IS NOT THEME

The one rule the code enforces rather than documents.

`course_terrain.height` decides where every support pier stops, and
`sloped/terrain.py` is an exact port of it that every production camera is
solved against. A profile that moved the grade, the terraces, the gorge, the
pads or the noise would invalidate both, silently, and the first symptom would
be a camera inside a mountain three sessions later.

So `validate()` rejects any profile carrying a terrain **shape** field
(`grade`, `steps`, `gorge_*`, `left_*`, `pads`, `noise`, `crest_*`, `edge_*`,
`cut_*`, `x_min`…`cell`). The `terrain` section may name materials and scatter
densities and nothing else.

> A theme repaints the mountain. It does not move it. Changing the landform is
> a *layout* change and belongs in `course_layout.gd`, where the camera port
> can be re-verified against it.

The rule is checked three ways: `validate()` complains, the scene prints those
complaints at build time, and a test asserts no profile in the registry carries
one.

### 2. Deltas inherit; `null` erases

`alpine_neon.json` is the root and the only file that has to be complete. Every
other profile names it in `extends` and carries deltas — a new theme is thirty
lines, not three hundred. Merging is deep, and a JSON `null` **erases** the
inherited key rather than shadowing it:

```json
"near_range": { "masses": null, "ring": { "count": 14, ... } }
```

That is how `canyon_dusk` drops the twelve hand-placed alpine masses and takes
a generated mesa ring instead. An empty list would still read as authored and
the generator would never run, so erasure has to be a distinct outcome.

### 3. The contrast pass is an overlay, not a fork

V21's readability retune used to be a set of `2.7 if v21 else 3.2` conditionals
inside `course_world.gd`. It is now `contrast.v21` inside the root profile,
merged on top after inheritance. Three consequences, all wanted:

* the V20 values are still in the file and still what an unflagged build gets;
* the pass **composes with any theme** — `canyon_dusk` gets the readability
  retune for free, and still wins where the two overlap;
* the pass's reach is now a diffable list, and a test pins it to the eighteen
  fields it was argued for.

### 4. Accent is a dial over values the profile owns

`accent.intensity` scales the zone practicals, the course spill, and any
emissive surface the profile itself overrides. It reaches nothing it cannot see
a base value for. A dial that silently scaled materials it had never been shown
would make two profiles with identical numbers render differently, which is the
one thing a data-driven system must not do.

---

## The schema

| section | controls |
| --- | --- |
| `id` `title` `family` `summary` `extends` | theme identity and inheritance |
| `sky` | procedural sky: top, horizon, ground, curves, sun angle, energies |
| `grade` | background energy, ambient, tonemap, exposure, white, contrast, saturation |
| `fog` | haze colour, energy, sun scatter, density, height falloff, aerial perspective |
| `ssao` `ssr` `glow` | the screen-space passes and the bloom curve |
| `lights` | the rig by name — `Key`, `WorldKey`, `WorldFill`, `WorldWarm`, `Rim`, `ValleyBounce`; colour, energy, specular, rotation, cull mask, shadow cascade. Energy `0` retires a light rather than adding it dark |
| `backdrop.near/mid/far_range` | distant masses: authored `masses`, or a generated `ring`; facets, tiers, taper, materials, base height |
| `backdrop.structures` | the landmark set — lit architecture on the crests |
| `backdrop.dusk_band` `backdrop.clouds` | the warm horizon and the depth-layering haze banks |
| `terrain.surfaces` | the four ground material keys (shelf, flank, cliff, high) |
| `terrain.scatter` | rock passes: count, clearance, gauge, two materials, accent frequency |
| `dressing.lamps` | service lighting along the course: spacing, offset, stock, lenses |
| `dressing.scrub` | vegetation clusters: target, slope limit, clearance, clump size, materials |
| `dressing.pylons` | crest installations; sites are relative to the terrain centre |
| `dressing.valley` | lit platforms on the gorge floor |
| `dressing.practicals` | the omni spill and the warm underlight along the track |
| `zones` | **zone integration hook** — one practical per race moment (`start`, `mix`, `obstacle`, `split`, `merge`, `finish`), by colour, energy, range and lift |
| `ravine.water` | reserved: a water plane keyed off the existing gorge. Visual only |
| `accent.intensity` | the one dial |
| `palette` | surface overrides by material key, in `lab_palette._retune`'s own vocabulary |
| `contrast` | named overlay passes, merged last |

Every section is optional in a delta. Only the root sets them all.

### The backdrop generator

A layer takes either authored `masses` (five columns: bearing, radius, height,
base radius, seed) or a `ring` spec that generates the same five columns
deterministically. Authored wins, because the alpine ranges were placed by eye
against a specific camera and no generator reproduces that; a theme with no
such study writes a ring and gets an arc.

**`taper` runs the other way from its name.** `hero_world._mass_point` documents
it: at `0.78` a mass is a cone, and a cone at two hundred units puts only its
foot in frame. A wall — or a mesa — keeps its width to the crest and wants
`0.22`–`0.34`. The first canyon draft used `0.88` and rendered a field of
traffic cones.

---

## Adding a theme

```bash
cp godot/assets/marble_machine/environment/profiles/mono_readability.json \
   godot/assets/marble_machine/environment/profiles/my_theme.json
# edit id, title, family, summary, and whatever you want to move
# add "my_theme" to profiles/index.json
python tools/sloped_environment.py check                       # no Godot needed
python tools/sloped_environment.py diff alpine_neon my_theme   # what you changed
python tools/sloped_environment.py sheet my_theme alpine_neon  # what it looks like
python tools/sloped_environment.py measure my_theme            # what it measures
```

`check`, `diff` and `show` never launch Godot and are the ones to run in a
loop while authoring. A typo in a material key is caught by `check` and by the
test suite, not by a `push_error` four minutes into a render batch.

---

## Measuring a theme

"Dark background, bright machine" is a claim about two populations of pixels,
and the scene has been able to separate them since the two-key rig was built:
the product is on visual layer 1 and everything this framework makes is on
layer 2. `--layers` points the camera at one of them, and at neither:

```
--layers=machine   visual layer 1: the course, the modules, the racers
--layers=world     visual layer 2: the terrain, the dressing, the ranges
--layers=sky       no layer at all: the sky, the haze and the grade
```

The sky frame is what makes the other two honest — both of them render the
background as well, so a pixel that matches the sky frame belongs to neither
population and is dropped.

> **One trap, found the hard way.** `Light3D` extends `VisualInstance3D`, so a
> camera culls lights by the same mask. Every light in the rig sits on the
> default layer 1, and the first `--layers=world` frame was an *unlit* mountain
> that measured thirty times darker than it is. `_isolate_layers` now puts
> every light on every layer before narrowing the camera, and only when
> `--layers` is passed, so no shipped render can reach it.

`python tools/sloped_environment.py measure`, over `long_track`, `split` and
`finish` at contrast `v21`:

| profile | world L | machine L | headroom | flat % |
| --- | ---: | ---: | ---: | ---: |
| `alpine_neon` | 29.5 | 49.0 | 19.5 | 0.37 |
| `canyon_dusk` | 26.6 | 49.1 | 22.5 | 0.37 |
| `glow_valley` | 11.6 | 49.4 | 37.8 | 0.58 |
| `mono_readability` | 18.1 | 52.6 | 34.5 | 0.29 |

`flat %` is the share of the finished frame that has stopped shading — the V21
pass's own measure, taken with `tools/sloped_contrast_measure.py`, so a theme
is judged by the instrument the film was graded with rather than by a new one
invented to flatter it.

The table earned its keep immediately: the first `canyon_dusk` draft measured a
world at **33.2** — *brighter* than the shipped one, with only 15.8 of headroom.
It looked wrong in the sheet and the number said why.

---

## The profiles

**`alpine_neon`** — the root, and the shipped V20/V21 direction transcribed
field for field. Cold dusk mountainside, warm horizon behind it, service
lighting along the course, lit industry in the gorge below.

**`canyon_dusk`** — red rock an hour before dark. The mountainside becomes
sandstone, the cold fill drops to half, the haze turns to dust, the crest
pylons go, and the backdrop is generated mesas rather than authored alpine
masses. Demonstrates: palette overrides, the ring generator, `null` erasure,
turning a dressing family off.

**`glow_valley`** — night, a near-black valley floor, and everything lit is lit
hard. Ten tall lit structures instead of six short ones, eleven valley
platforms, violet beacons, accent at 1.45. The strongest statement of "dark
background, bright machine" the schema can make **without touching the
machine** — the course's own materials are identical in all four rows.

**`mono_readability`** — not a look, an instrument. Every environment surface
goes to one neutral value, every environment accent goes out, the machine is
untouched. Whatever still reads in this frame is the course itself, so it
answers silhouette and track-readability questions that a lit, coloured,
dressed world can hide.

---

## Proof

`docs/validation/sloped_race_v1/v23_environment/`

* **`profile_sheet.png`** — four profiles × three shots. One course, one seed,
  one camera, one layout, one contrast pass; the only thing that changes
  between rows is `--environment`.
* **`layer_split.png`** — one frame as three populations of pixels.

### Render neutrality

The claim that matters most for a refactor this wide is that it changed
nothing. `python tools/sloped_environment.py neutral --reference <checkout>`
renders four sections under both contrast passes from this branch and from a
pristine checkout of `origin/main`, and compares the files byte for byte:

```
  v20       start       identical
  v20       long_track  identical
  v20       split       identical
  v20       finish      identical
  v21       start       identical
  v21       long_track  identical
  v21       split       identical
  v21       finish      identical
```

Eight of eight. The same property the style lock proved for the additive style
system, and the reason that system could be trusted afterwards.

### Tests

`tests/test_sloped_environment.py` — 42 tests: the registry, inheritance,
`null` erasure, the contrast overlay, the accent dial's reach, GEOMETRY IS NOT
THEME, the ring generator, the two readers agreeing, and that every material
key any profile names exists in `lab_palette.gd`.

`tests/test_sloped_contrast.py` — two tests were rewritten rather than deleted.
They used to read `2.7 if v21 else 3.2` out of `course_world.gd`; they now
assert the same guarantee where it now lives — that the root profile resolved
with no contrast pass *is* the V20 rig, field for field. A third test was added
pinning the overlay to the eighteen fields V21 was argued for.

The rest of the suite is unchanged: same failures as `origin/main` (`pymunk`
and `pybullet` are not installed in this interpreter), no new ones.

---

## How a future race map uses it

Nothing in the profile system knows about layout B, seed 5432, or this course.

* **A new course on the same theme** builds its layout table as usual and
  passes the resolved profile through `Machine.build(..., {"environment": p})`.
  Pylon sites and scrub spans are authored relative to the terrain centre, so
  they follow a layout whose centre is elsewhere.
* **A new theme on the same course** is a JSON file and a line in `index.json`.
* **A zone a course does not have** is skipped — `_practicals` builds a lamp
  only where the layout has a node of that name, so a profile written against
  one course does not have to be edited to run on another.
* **A course with different zones** adds them to `zones` and to its layout
  table; no code changes.

---

## Integration notes for V23

1. **`--environment=` reaches the race scene for free.** `sloped_race_scene.gd`
   extends `course_scene.gd` and options flow through `OS.get_cmdline_user_args`,
   so every production tool that shells out to a render scene can pass it
   without a code change. It is not wired into `tools/sloped_short.py` or the
   Short's edit list yet — that is a deliberate omission, because choosing the
   Short's theme is an art decision and this branch is not making it.
2. **The default is the ship look.** No tool that does not pass
   `--environment=` behaves differently, and the eight-frame neutrality proof
   is how that is known rather than assumed.
3. **The contrast pass still gates on `_contrast`.** `sloped_race_scene`'s
   `DEFAULT_CONTRAST = "v21"` is untouched, and V21 composes with any theme.
4. **Physics, seed, race structure, country skins and V22.1 timing are
   untouched.** The profile system cannot reach any of them: it has no access
   to the replay, the layout runs, the marble materials or the edit list, and
   the one field that could have leaked into the simulation — terrain height —
   is the field `validate()` refuses.
5. **What is not themable yet**, and should be considered before V23 art work:
   * the **machine's own materials** — pearl, acrylic, graphite, the marble
     colours. Deliberate: a country skin and a theme must not fight over the
     same key. If V23 wants a themed machine it needs a *second* profile kind
     with its own rules, not a widening of this one.
   * the **camera rig** — shots, lenses and the chase solver are V22.1's and
     stay there.
   * `ravine.water` is reserved in the schema and does nothing yet.
   * the dressing **forms** are fixed; a profile chooses their materials,
     counts and placement, not their geometry. A theme that needs a different
     silhouette of lamp mast needs a new builder, and that is the right place
     for the next increment.

---

## Files

| file | change |
| --- | --- |
| `godot/assets/marble_machine/environment/environment_profile.gd` | new — load, inherit, overlay, accent, validate, ring generator |
| `godot/assets/marble_machine/environment/environment_builder.gd` | new — a resolved profile to scene |
| `godot/assets/marble_machine/environment/profiles/*.json` | new — the registry and four profiles |
| `godot/assets/marble_machine/course/course_world.gd` | rewritten as a delegating seam; its constants moved to `alpine_neon.json` |
| `godot/assets/marble_machine/course/course_terrain.gd` | `scatter` takes its two materials and accent frequency from the caller |
| `godot/assets/marble_machine/course/course_dressing.gd` | every family takes a spec; each can be turned off; pylon sites relative to the terrain centre |
| `godot/assets/marble_machine/course/course_machine.gd` | folds the profile's ground fields into the terrain table; drives the scatter passes |
| `godot/assets/marble_machine/lab_palette.gd` | `apply_environment()` — surface overrides, applied after the V21 retune |
| `godot/scripts/course_scene.gd` | `--environment=`, `--layers=`, resolves once and passes down, zone practicals from the profile |
| `sloped/environment.py` | new — the Python reader |
| `tools/sloped_environment.py` | new — list / check / show / diff / sheet / measure / neutral |
| `tests/test_sloped_environment.py` | new — 42 tests |
| `tests/test_sloped_contrast.py` | two tests rewritten against the profile, one added |
