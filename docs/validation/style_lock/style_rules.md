# SLOPED RACE COURSE — LOCKED VISUAL DESIGN SYSTEM

Branch `marble-style-lock-lab`, from `marble-sloped-course-lab` at `62edcb9`.

This document is the style lock. It says what the final product looks like,
what every value is, and — the part that matters for anything built later —
*why* each value is what it is. The renderer is the arbiter: every number
below was rendered and looked at, and the ones that are here instead of the
obvious ones are here because the obvious ones were tried and failed.

**No geometry a marble can touch was changed.** No centreline moved, no
channel width moved, no route changed, nothing simulates. Section 7 lists the
geometry changes that *would* help, for whoever owns that code.

---

## 1. THE LOCK

```
track = pearl      guard = cast_low      support = brass
env   = valley     finish = gold
```

Applied with one flag, from anywhere:

```bash
python tools/style_lab.py board          # the locked style, 1080x1920
$GODOT_BIN --path godot scenes/CourseRender.tscn -- --style=lock ...
```

Five axes, selected independently (`--track=`, `--guard=`, `--support=`,
`--env=`, `--finish=`). Every axis defaults to `base`, and `base` on every
axis is a no-op — so `tools/course_lab.py` still reproduces the frames this
branch inherited, unchanged.

| axis | locked | what it is |
|---|---|---|
| track | `pearl` | warm pearl shell off the clip point, cool silver running band, deep keel |
| guard | `cast_low` | 15 % aqua, 0.40 rim, 0.72 self-emission — pigment capped by a measured occlusion constraint |
| support | `brass` | lifted matte graphite, moulded brass caps |
| env | `valley` | near ground on its own light layer, sky-sun dusk, ridge silhouette, lit settlement |
| finish | `gold` | hotter gold wash, hard checker, cool start sign left alone |

---

## 2. THE PALETTE

`final_palette.png` is the swatch document and `material_values.json` is the
same data as JSON. Both are written by the renderer itself — `--dump-style`
resolves every swatch out of the live palette *after* the machine is built,
so a swatch is a value that actually rendered rather than a hex retyped into
a sheet.

The colour journey runs **down the course**, not down a tower:

```
  START      cyan on white pearl          #54E6F7 line, #D8D4CB shell
  UPPER      cyan, cooling                #54E6F7 line
  MIX        violet                       #9B6BFF line and ring
  OBSTACLE   orange machinery             #F0813A
  SPLIT      blue against orange          #3FA8FF / #F0813A, painted shells
  MERGE      gold                         #F3CE86 line
  FINISH     gold wash on warm pearl      #FFC062 wash, #D6CDB8 shell
```

Structure is one family end to end (`#333A44` matte graphite, `#181C23`
deep), and warm hardware is one family end to end (`#C89A4C` brass). Rock is
four nearly-equal cool values plus two darker scatter values. That is the
whole system; there is nothing else.

---

## 3. THE RULES

Fifteen rules. Each one is a mistake that was made and measured — on this
branch or, for R7's cap, on a parallel one — stated so it does not have to be
made again.

### Material

**R1 — Quote colours as hex, never as floats.** GDScript colour floats are
sRGB; `0.605` is linear 0.31, a shade under a grey card. (Inherited from the
toy style lock and still correct.)

**R2 — Albedo × key energy has to land under the tonemapper's shoulder.**
With this rig (key 2.7, `tonemap_exposure` 0.86, ACES) a moulded surface
meant to read as *bright but not white* tops out near **`#D8D4CB`**.
`#E8E6E0` — the shipped pearl — is linear 0.79, and 0.79 × 2.7 is far past
the shoulder, so the shell, the rolled lip and the polished floor all resolve
to the same white and the six-feature section reads as one painted road.
Premium pearl needs a *lower* albedo than the word suggests; the gloss comes
from the clearcoat lobe.

**R3 — Nothing is `metallic 1.0`.** A metallic surface trades diffuse for
environment reflection, and this scene's reflection source is a nearly black
dusk sky. Warm hardware is **moulded with `metallic ≈ 0.34`** and
`metallic_specular ≈ 0.78`. The shipped support caps and track rib blocks
used `_metal` and rendered dull olive — every gold accent on the course was
invisible for this reason alone.

**R4 — A running surface is part metal with a *small* clearcoat.**
`metallic ≈ 0.55`, `roughness ≈ 0.24`, **`clearcoat ≈ 0.45`**. The shipped
value was `clearcoat 1.0`, and a second full-strength gloss lobe on a wide
sky-facing cradle is what made the running band white — not the metallic
term, which was already correct.

**R5 — Structure is matte *and low-specular*.** `roughness ≈ 0.58`,
`clearcoat_enabled = false`, **`metallic_specular = 0.12`**. A pier is a
vertical cylinder and the rim light rakes in nine degrees above the
horizontal at `light_specular 1.5`, so it lays a bright stripe down every
leg's full length, and every pier reads as a polished steel tube. This took
three attempts:

1. raising roughness from 0.42 to 0.62 made it *worse* — a broader lobe
   spreads the stripe across more of the cylinder rather than dimming it;
2. dropping the clearcoat removed only the second, thinner lobe on top;
3. `metallic_specular` is the dielectric F0 scale in Godot 4 and applies to
   non-metals, so at 0.12 the stripe goes and the rim keeps its full
   strength on the pearl channel, which is what it is there for.

The general form: **when a highlight is too bright, roughness changes its
shape and `metallic_specular` changes its intensity.** Reaching for
roughness first is the mistake, and it was caught only because the fault
appeared identically on all four support candidates — a fault common to every
candidate on an axis is never in the candidates.

**R6 — An emissive line runs at energy 4.6 to 6.0.** Not 8 to 10. Above
that the line's core clips and its hue survives only in the bloom halo, so a
cyan start, a violet mixer and an orange choice all render as white lines
with coloured fog around them. The zone story was authored correctly on the
inherited branch and then burnt off.

**R7 — A guard buys its presence from *emission*, not from pigment.**
15 % alpha and 0.72 self-emission. Pigment averages away in a downscale;
emission does not — so of the four single-idea candidates, `tint` (30 %) and
`glass` (40 %) both lost the rail at 390 pixels while `lit` (22 % + emission)
kept it.

The pigment ceiling is not an aesthetic choice, it is a measurement from
another session on this same course: **the acrylic's top arris stands 0.23
above a 0.285 marble's crown**, so clearing it side-on needs 18.2° of camera
elevation in the far lane, 26.6° in the centre and 46.4° in the near one —
while every section camera on the shot list sits between 9° and 33°. A racer
in the near half of the channel is therefore *always* seen through the rail,
and that branch capped guard alpha at 0.150 for exactly that reason.

Rendering both settles it and the constraint turns out to cost nothing. At
34 % the rail visibly washes an orange racer to pale cream where it crosses
it; at 15 % the racer keeps its colour. And the low-pigment rail reads
*better*, not worse — 0.72 emission makes a crisp bright aqua line where 34 %
pigment made a broad milky band. See
`guard_occlusion.png`.

### Light

**R8 — The near ground and the distance are lit separately.** Layer 1
product, layer 2 distance, **layer 4 near ground**. The shipped build put the
heightfield on the world layer, so `WorldWarm` — the amber rake that exists
to warm the far ranges — hit the mountainside under the track at full energy
and turned it tan. Splitting the layer is the single change that produces the
warm-distance / cool-foreground depth the target concept has.

**R9 — Exactly one light draws the sun, and it lights nothing.** Every
functional light is `SKY_MODE_LIGHT_ONLY`; one `SKY_MODE_SKY_ONLY` light is
the dusk, aimed **along the camera's own bearing** (yaw = the sun's bearing,
pitch = minus its elevation). A `ProceduralSkyMaterial` draws a disk for
every directional light that includes the sky, so the shipped rig was
carrying six overlapping glows, all of them *behind* the camera — because the
warm rake has to come from +X +Z or it lights only the uphill faces this
course's cameras never see.

**R10 — `fog_sun_scatter` is multiplied by every directional light.** With
six lights at energies 1.2 to 2.7 it has to be **≤ 0.15**. At the inherited
0.52 the far valley floor renders as a bright pale sheet however dark the fog
colour is set, because at 1400 units the fog is 93 % opaque and nearly all of
what it carries is scattered key light. Behind the finish arena this took the
background from median luma **157 to 75**.

**R11 — A rim light needs a cull mask.** The shipped `Rim` had none, so a
cyan light at `light_specular 1.5` was rimming every boulder and terrace lip
on the mountain, which is why the ground scatter reads as teal litter. A rim
light belongs to the subject: mask 1.

### Environment

**R12 — No lit slab is ever a sky.** A horizon is infinite and a slab is
not. Raised until it cleared the far range, the inherited nine-slab dusk band
read as exactly what it is: rounded-rectangle billboards with a seam every
ten degrees, brighter than the finish arena. Horizons come from the sky
material and its sun.

**R13 — No thin slab is ever a cloud.** Fourteen 190 × 13 × 26 boxes seen
almost edge-on from a camera pitched fifteen degrees down are fourteen thin
plates with razor-straight top edges hanging in the sky. Crop the top of the
hero frame and enlarge it and those plates — not the ranges, not the terrain
— are every hard geometric edge above the skyline. Haze comes from the fog's
height term (`fog_height -26`, `fog_height_density 0.030`).

**R14 — A ridge silhouette is sized against the massif, not against the
other ranges.** The course sits on a flank whose crest reaches y 62 at 90
units out, and the hero lens is solved to fit the course with a 9 % margin —
so there are about three degrees of sky above the skyline, and all three of
`course_world`'s rings, authored to top out between y −28 and y +48, have
always been hidden behind the hill the course is on. A ridge that reads has
to stand taller than the hill in front of it. Two numbers set it: *height*
puts the crest three degrees below the camera's own elevation, and *base
radius* decides peaks or wall — at 72 against an 18° spacing eight masses
merge into one silhouette, at 53 the gaps are where the dusk shows through.

### Zones

**R15 — `sign_face` is the START gantry.** It is not the finish arena's
sign; `course_finish` lights its own face with `lit_gold_wash`. The only user
of `sign_face` on the whole course is `course_modules.start`, and warming it
for the finish pass turned the start sign gold — inverting the one thing the
zone story exists to do. The frame's warmest pixels belong to the finish
arena and nowhere else.

---

## 4. THE CHOICES, AND WHY

### Track — `pearl`

Compared on a lens added for the purpose (`material`, elevation 25, bearing
58) plus an underside band (`underside`, elevation −4). Every other shot in
the table is framed on a race moment at a bearing of 16 to 44 degrees, where
the surface facing the camera is the channel's *outer shell wall* — so a
comparison of running-surface materials made from any of them compares the
one surface that never changes. That was the first track sheet, and it was
worthless.

| | pearl vs silver | roughness | highlight | underside | edge | guard |
|---|---|---|---|---|---|---|
| `base` | one white | 0.19/0.17 | clipped band | none — belly is pale | lost in bloom | rail invisible |
| **`pearl`** | **warm shell, cool band** | **0.30/0.24** | **broad, unclipped** | **`#191D24` keel** | **holds hue** | **aqua reads against warm pearl** |
| `silver` | cool shell, cool band | 0.26/0.22 | crisp, cooler | good | holds hue | aqua on cool silver — less separation |
| `fascia` | warm shell, soft | 0.33/0.30 | softest, nearly matte | best — `#0E1116` | holds hue | good, but the channel loses its gloss |

`pearl` wins on the one criterion that decides it: **the section's three
surfaces have three different values**, so the moulded profile the channel
was designed around is visible, and a candy-coloured racer sitting in a
`#7F8B99` cradle pops.

`silver` failed for a more specific reason than "it looks grey", and the
sheet is what showed it. The break between shell and running band is carried
by **hue contrast as much as by value** — a warm shell against a cool band.
Take the warmth out and the two are both cool greys three steps apart, and
at any framing wider than a close-up they merge back into one surface. So
matching the concept's literal "Light Silver / Gray" swatch *destroys* the
section separation that swatch was supposed to describe. The concept's
channel is warm-lit silver, not neutral silver.

`fascia` has the best underside contrast and the least premium finish; at
`clearcoat 0.20` it reads as painted rather than lacquered, and the running
band nearly disappears.

### Guard — `cast_low`

`base` (12 % on a 0.26 wall) is below the resolution of every camera on this
course: the aqua rail that is one of four things the target concept reads at
a glance is simply absent. Of the three single-idea candidates, `glass`
(40 %) gave the strongest tint and the best thickness, and `lit` (22 % +
emission) was the only one still visible at 390 pixels.

`cast` combined them at 34 % pigment and 0.40 emission, and was then
**superseded on an occlusion measurement rather than on looks** — see R7.
`cast_low` moves the pigment to the 0.150 cap that measurement sets and
spends the difference on emission (0.72) and rim (0.40). It is better on both
counts: near-lane racers keep their colour through the rail, and the rail
itself reads as a crisper aqua line. `cast` is kept in the table because it
is the right recipe if the guard geometry ever changes and the constraint
lifts.

| | tint | opacity | edge highlight | thickness feel | at 390 px |
|---|---|---|---|---|---|
| `base` | `#7FE0E8` | 0.115 | rim 0.30 | none | **absent** |
| `tint` | `#63D2E0` | 0.30 | rim 0.44 — frosted, reads as a bright line | moderate | fades |
| `lit` | `#6FDCEA` | 0.22 | rim 0.36 + em 0.55 | weak | holds |
| `glass` | `#3FBACC` | 0.40 | rim 0.26 — none, by design | **best** | fades |
| **`cast_low`** | **`#63D2E0`** | **0.15** | **rim 0.40 + em 0.72** | moderate | **holds, crisply** |

All five guard identities move together (neutral, blue route, orange route,
finale, bowl); a split whose blue rail is cast glass and whose amber rail is
a lit strip reads as two products. The thickness read is the one thing
`cast_low` gives up, and it cannot be bought back with pigment — only with
geometry, which R7 and §7 say not to touch.

### Support — `brass`

`base` piers are near-black hairlines with dull olive caps (R3). `mono` — two
tone graphite, cool cap, no warm accent — is the control for "not too busy",
and it is genuinely cleaner and genuinely worse: the frame loses its only
structural warmth and the whole machine goes cold. `copper` was rejected on a
specific ground rather than on taste: **a copper cap is close enough to the
orange route's identity colour to compete with it**, and the split's two
routes have to be the only orange thing in the lower frame. Brass reads as
gold hardware, which is what the concept's own swatch calls for.

Also in this axis, because it is support appearance: the trackside lamp
masts. At 0.10 stock the column is a hairline that averages away in the
resize and leaves its foot block reading as a dark box hanging on a wire —
the most debug-looking detail in the inherited section frames. Stock 0.145,
and the foot scaled at 4.3 × stock rather than the 6.2 the base ratio works
out to: thickening the column and scaling the foot with it linearly preserves
the very proportion that caused the problem.

### Environment — `valley`

`base` is the diagnosis in one frame: amber rake on the near ground (tan
mountainside), mauve haze over blue rock (the muddy cast), unmasked cyan rim
(teal scatter), and a dusk band hidden behind a mountain (no warm horizon).

`depth` fixes the light rig, the haze and the sky — that is most of the gain,
and it is the cheapest cherry-pick if only one thing can be taken.

`valley` adds the scenic pass on top: the inherited cloud slabs and dusk band
switched off (R12, R13), a ridge silhouette sized against the massif (R14),
lit settlement on the near crests, the nearest range pushed out by a third so
its thirty facets stop reading as flat plates, and a darker near ground for
the pearl channel to be bright against. It is the lock.

The seven things the brief asks of an environment, and where each one lives:

| requirement | how |
|---|---|
| cliff silhouettes | `_ridge_line`, eight 46-facet masses at radius 288-330, crests three degrees below the camera, spaced so the dusk shows between them |
| haze layering | fog height term (`fog_height -26`, `fog_height_density 0.030`) pooling in the gorge — geometry was tried and rejected (R13) |
| depth | four distances at four separated values: near ground `#1D2530`, ridge `#141B26`, mid `#22344B`, far `#3B5877`, plus `fog_aerial_perspective 0.62` |
| warm distant lights | six `_settlement` clusters on the near crests at bearings 160-246 — the arc every camera on this course looks along — each with lit window bands and one warm ember at its foot |
| vegetation / scrub massing | inherited `_scrub`, retuned darker (`#16221C` / `#1F2018`); under the near-ground warm rake the shipped values came back as bright moss chips lying on a blue hillside |
| valley feel | the gorge on +X falls 28 units and the haze pools in it; the massif fades to `edge_y -82` past radius 94 |
| warm / cool balance | cool by light (near ground on layer 4 at 0.85 warm energy against `#5F8CBA` fill), warm by sky (one `SKY_ONLY` sun at bearing 202) and warm by object (brass hardware, gold finale) |

`warm` is the counter-proposal — warmth in the ground itself rather than only
in the light on it. It is cohesive and it was rejected: it spends the
temperature contrast that was buying the depth, the mountainside goes dusty
maroon, and the sky competes with the finish arena for the frame's warmest
pixels (R15).

### Finish — `gold`

`base`'s gold fascia already reads; its checker does not — two near-neutral
tiles under a warm wash converge. `gold` separates them hard (`#EDE2CB`
against `#0D1014`), which is what makes the checker area legible at phone
width, and raises the wash from 2.1 to 2.4.

That wash increase is also how the FINISH sign got readable: the arena lights
its own sign face with `lit_gold_wash`, so the sign and the zone brighten
together and there is no separate dial for one (R15 — `sign_face`, the
obvious-looking dial, is the START gantry and warming it broke the start
zone). `pearl_warm` came *down* at the same time, from `#E3DBCA` to
`#D6CDB8`: the arena shell was the brightest large surface in the frame and
was competing with its own gold.

`contrast` — the same gold with the arena shell pushed cool — is cleaner and
less of an occasion; the gold reads as an outline around a cool deck rather
than as a warm zone, and the finish stops being the frame's warm destination.

### Where this still falls short of the target

Named because `target_comparison.png` makes them visible and a style lock
that only lists its wins is not a lock.

**The violet zone has no object.** The concept's violet is a mixing bowl —
a large transparent form glowing violet, and one of the four things the eye
picks out. On a sloped course the violet zone is a length of edge light on
`leg3` and a practical over the mixer module, so the temperature story is
complete and the *presence* is not. Fixing it needs a violet-lit form at the
mix node, which is geometry.

**Detail density is lower.** The concept populates its structure with
railings, walkways, small machinery and figures. Ours has masts, cairns,
scrub and ribs. That gap is deliberate at this stage — every one of those is
geometry — but it is the main reason the concept reads as busier and more
inhabited at the same distance.

**Ours is darker.** The concept is a lit product photograph with a dark
background; this is a dusk landscape with a lit product in it. That is the
right call for a course installed on a mountain and it should be a conscious
one, not a drift: if a brighter frame is wanted, `tonemap_exposure` (0.86)
and `ambient_light_energy` (0.46) are the two dials, and R2's albedo ceiling
moves with them.

---

## 5. PHONE CHECK

`phone_check.png`, rendered at 1080 × 1920 and resized to 390 CSS pixels —
what a phone viewer actually receives — plus a row of 1:1 crops, because a
resize hides whether a feature is thin or merely small.

| question | verdict |
|---|---|
| does the route read? | **yes** — the switchbacks separate, and the edge lights make the length legible |
| are the marbles readable? | **yes** — candy hues against a `#7F8B99` cradle, which is what the darker running band is for |
| are the split colours obvious? | **yes in the hero frame**, where blue `#2E8FD8` and orange `#F0813A` run side by side as painted shells rather than tinted pearl. **Not in the `split` frame** — that lens fills itself with the blue gate and leaves the orange one on the right edge. The style delivers the read; the `split` lens does not frame it. Camera item, listed in §7. |
| is the finish zone clear? | **yes** — it is the only warm zone and the only checker |
| does the environment add beauty, not clutter? | **yes** — the scenic pass is silhouette, haze and temperature, which survive a downscale, rather than small objects, which do not. The settlement and the scatter are gone by 390 px and cost nothing when they go |

---

## 6. WHAT TO CHERRY-PICK

In dependency order. Everything is additive; nothing rewrites an existing
value.

1. **`godot/assets/marble_machine/lab_palette.gd`** — `override()`,
   `has_override()`, the five `make_*` builders, and four aliases
   (`keel_graphite`, `strut`, `strut_deep`, `strut_accent`) whose base values
   are *identical* to the shared keys they stand in for. Changes no rendered
   value; it is what makes the axes separable.
2. **`godot/assets/marble_machine/course/course_style.gd`** — new file, the
   whole system. Self-contained.
3. **`godot/assets/marble_machine/course/course_machine.gd`** — two lines:
   the track's keel and the supports now ask for the aliases.
4. **`godot/scripts/course_scene.gd`** — the five options, the four `Style.*`
   calls, `--dump-style`, and two additive shots (`material`, `underside`).
5. **`godot/assets/marble_machine/course/course_dressing.gd`** — mast stock
   as a parameter, default 0.10 (unchanged).
6. **`tools/style_lab.py`** — new file. `tools/course_lab.py` is untouched.

The evidence sits beside this file: five candidate sheets, the board, the
palette, the phone check, the target comparison, `guard_occlusion.png` and
`material_values.json`. `_frames/` is gitignored, in the same way as the
other labs' `_preview/` directories — it is the working set and it changes
every render.

Safe because the default is `base` on every axis and `base` is a no-op. If
only one thing can be taken, take **`env=depth`**: the layer split, the
masked rim, the sky sun and the fog scatter are four one-line fixes that
carry most of the visible gain and touch no material.

---

## 7. DEFERRED — GEOMETRY AND CAMERA

Documented, not done, because they are outside this session's scope.

**Guard height (physics), and it cuts the other way.** `GUARD_HEIGHT` is
0.26 with the wall standing on the lip, and the rail now reads by emission
rather than by thickness. Do **not** raise it to buy silhouette: the arris
already stands 0.23 above a marble's crown, and raising it raises the camera
elevation needed to see a near-lane racer over it — across the whole shot
list. If the guard is ever revisited, *lowering* it is what would let the
pigment come back up. Either way it is a wall a marble bounces off, so it
belongs with whoever owns the colliders.

**The `split` lens (camera).** It frames the blue gate and pushes the orange
one to the right edge, so the single most important read on the course — that
this is a *choice* between two routes — is not in the shot named after it.
Both routes are legible side by side in the hero frame, so this is framing
and not colour. A bearing swung the other way, or a wider extent, fixes it.

**The finish lens (camera).** `finish` is framed at elevation 21, bearing 34,
and roughly 40 % of its frame is empty valley haze above the arena. The haze
is now dark instead of white (R10), but the composition is the actual fault
and it is a camera decision, not a material one.

**`course_world.STRUCTURES` is dead geometry.** Six lit slab towers at radius
316 to 352 with their rooflines near y −6, standing behind a near range that
reaches y +40, which is itself behind a massif whose crest reaches y 62. They
have never been visible from any camera on this course. Either delete them or
re-site them the way `course_style._settlement` does.

**Heightfield cut faces.** At the `long_track` framing the bench cut still
shows straight-edged facets where it meets the flank. Three nearly-equal rock
values were the right answer for the *bands*; the remaining edge is the
surface itself and wants either a finer cell or a normal map.

**The mast arm kinks.** `Geometry.tube` from the column top to a point 1.30
back and 0.34 up is a two-segment elbow. From directly behind it reads as a
bracket. A three-point sweep would fix it; it is dressing geometry, so it is
cheap whenever someone is in that file.

---

## 8. NOTES FROM THE PARALLEL SESSIONS

Two other sessions were live on this course while this branch was authored.
Where their findings touch the style lock:

**`marble-sloped-presentation-polish`** measured the guard-occlusion geometry
quoted in R7, and this lock's guard alpha is set by it. That branch also found
three pre-existing bugs on `marble-sloped-course-lab` that are worth knowing
before trusting anything here:

- `course_scene` and `course_machine` each call `Layout.table`, which
  deep-copies, and only the machine's copy is given `cut_index` — so **every
  `Terrain.height` query from the camera rig reads the un-benched hill**, up
  to `cut_depth` too high along the racing line. This lock is unaffected
  (nothing in `course_style.gd` queries the terrain), but the section
  cameras' side-probe is, and their branch fixes it.
- `_dusk_band` orients slabs with `look_at` *before* they join the tree,
  which no-ops — so seven of nine warm slabs were never drawn. This lock
  switches that group off entirely and uses no `look_at` anywhere, so it
  cannot inherit the bug.
- `Track.build` receives `name.capitalize()`, and GDScript inserts a space
  before a digit, so `leg1` becomes node `Leg 1` and the reverse
  `_spec_for("leg 1")` lookup falls back to `runs[0]`. Latent only because
  the launch and all three legs share `HERO_SCALE`.

Their art findings agree with this branch's independently on the two that
matter: the blown-out white channel was **the clearcoat lobe, the 3.2 key and
a glow threshold sitting under the pearl** (R2, R4, and the 1.16 → 1.55
threshold change), and the tan flank has a second cause beyond the
light-layer fix — `WorldWarm` at −8° elevation lands on broad planes, not
only on edges, which is why this lock also cuts its energy on the ground
layer to 0.85.

---

## 9. HOW TO REPRODUCE

```bash
export GODOT_BIN=".../Godot_v4.7.2-stable_win64_console.exe"

python tools/style_lab.py candidates    # the five candidate sheets
python tools/style_lab.py board         # locked style, board, phone, target
python tools/style_lab.py palette       # swatches, from the live dump
python tools/style_lab.py all           # all of it, ~20 builds

python tools/style_lab.py axis track     # one sheet
python tools/style_lab.py one --shot material --set track=silver
```

Each candidate sheet varies **one** axis and holds the other four at the
lock, so a sheet answers "pearl or silver" rather than "sheet 1 or sheet 3".
Candidate panels render at 560 × 996; only the board, the phone check and the
target comparison pay for full resolution.

`style_lab.py` asserts the style the scene reports back against the style it
asked for, so a panel labelled `pearl` that rendered `base` fails the run
rather than reaching a sheet.

### The additive claim is proved, not asserted

All eight section shots were rendered twice at 1080 × 1920 — once from this
branch with no style options, and once from a throwaway detached worktree at
pristine `62edcb9` — and compared by SHA-256:

```
shot         this branch (no style) vs pristine 62edcb9
hero         IDENTICAL      obstacle     IDENTICAL
start        IDENTICAL      split        IDENTICAL
descent      IDENTICAL      final_run    IDENTICAL
long_track   IDENTICAL      finish       IDENTICAL
```

Eight of eight, byte for byte. The renderer is also deterministic: two
consecutive passes of the same three shots came back with identical hashes,
so the comparison means what it says. `physics_layout.json` matches on every
physical value; its only difference is `cameras` going from 10 entries to 12,
because two lenses were added to the shot table.

**Two of the inherited committed frames are stale.**
`docs/validation/sloped_course/start.png` and `descent.png` do *not*
reproduce from `62edcb9`'s own code — the pristine worktree renders them
differently too (`start` almost entirely, a camera distance and offset;
`descent` in 28 pixels by at most 3 levels). They were rendered before the
final code state on that branch and never re-shot. Nothing on this branch
caused it, and re-rendering them is that branch's call, not this one's.
