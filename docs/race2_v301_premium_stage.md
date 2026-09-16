# V30.1: the contained stage, made premium

**Branch** `v301-premium-stage-art-polish`, from `origin/v30-contained-stage-v2`
at `1d0800f`.
**Scope** surfaces, module sizes and where warm light is let into the
building. No physics, no camera, no course, no architecture.

---

## 1. What the V30 film actually looks like

The brief's review is right on every count, and two of its four points turn out
to have the same cause.

**The floor is a giant industrial grate.** From about 6 s the repeated narrow
strips are the strongest pattern in the frame, and by the final sprint they are
the frame. The numbers behind it were never taken: V30 sized its module against
the *frame width* — which only ever argues for a finer module — and landed on a
2.2-unit plate on a 0.18 gap. At camera A's median 12.04 units a second that is
**5.06 seams a second**. Nothing in the V30 toolchain computed that.

**The room is not neutral, it is teal.** V30's own hue test reports
`blue_over_red` 1.18 against a 1.35 threshold and concludes the cast is fixed.
The delivered final sprint renders its *lit floor* at RGB(60, 111, 119) — a
teal at chroma 0.49, green-to-red 1.84, blue-to-red 1.97.

**Several wall faces are large, flat, dark rectangles.** The marker render is
specific about which: `hall_panel` is ~50% of the hook frame, all of it the
near flank, and the black mass filling a third of the central chase is the
`drum` bay's 26 × 17 back in `hall_panel_dark` at #1D1A16.

**The warm practicals feel placed rather than built in.** They are 17 × 0.55
bars sitting 0.15 proud of the deck. And — see §5 — five of the nine are not in
the film at all.

---

## 2. The two findings this pass is built on

### 2.1 The floor's colour was never controlled by its albedo

V30 diagnosed the cast as the ACES toe and pre-compensated: it authored the
floor albedo warm (`#443A2C`) until the *average* came out neutral. The average
did. The picture did not.

The mechanism is `metallic_specular`. `lab_palette._matte` never sets it, so
every V27 and V30 room surface carries Godot's **0.5 default**, and at the
20–58° below horizontal this lens sees the floor at, that dielectric term is
**half the frame's brightness**: setting it to zero takes the sprint frame from
mean luma 67.1 to 35.3.

Nine probe renders place that term outside everything V30 suspected. It is
unchanged by removing **every light in the rig**, by a black sky, by a **red sky
at full energy**, by zero ambient, by no fog, and by zero background energy. The
floor still renders at RGB(23, 98, 108) with nothing lighting it.

| floor specular | G/R | B/R | chroma | sprint mean luma |
|---|---|---|---|---|
| **0.50** (V30, the `_matte` default) | 1.84 | 1.97 | **0.492** | 67.1 |
| 0.30 | 1.69 | 1.78 | 0.440 | 62.3 |
| 0.20 | 1.31 | 1.38 | 0.274 | 61.9 |
| **0.10** (V30.1) | 1.06 | 1.25 | **0.201** | 65.9 |
| 0.00 | 1.04 | 1.17 | 0.147 | 79.5 — flat, no form left |

**An albedo pre-compensation can only ever steer the diffuse fifth of such a
surface.** That is also why the brief's "do not fight it by making the floor
darker" is the right instruction: darker was never the lever, and V30's own
sweep recorded the cast getting *worse* every time it was tried.

**And this dissolves V30's stated trade-off.** Its §9.2 says "in this pipeline
you can have a neutral floor or a dark floor, not both". Once the specular is
0.10 the floor's hue is set by its albedo, so both are available at once:
V30.1's room is **darker** than V30's (42.0 against 46.3), **more neutral**
(bright-quartile chroma 0.202 against 0.371) and **more readable** (racer
separation 91.8 against 87.9).

### 2.2 V30's hue test could not see it

`race2_v30_review.measure` takes `blue_over_red` as a ratio of channel means
over every room pixel above luma 20. A floor made of bright panel tops
separated by dark shadow has most of its *pixels* in the shadow and all of its
*colour* in the tops, and hue is a property the eye reads where the picture is
bright.

| the same final-sprint frame | blue/red | chroma |
|---|---|---|
| V30's measure, all lit room pixels | 1.18 | 0.355 |
| the room's brightest quartile | **1.97** | **0.49** |

V30.1 reports both. The average is not wrong — it is the right number for "is
the room blue" — it was never the right number for "is the floor blue".

---

## 3. What is locked, and the check that it stayed locked

Not one architectural number moves. `tests/test_race2_v301_stage.py` asserts
these against **V30's own profile** rather than against literals, so the two
cannot drift apart silently:

| | |
|---|---|
| wall radii | 56 near flank, 70 deep rear, 60 far flank, 70 upper |
| band arcs | 90–150, 150–210, 210–255, 75–240 |
| heights, feet, thicknesses, batters, counts | V30's, field by field |
| pylon ring | 8 columns, r = 48, bearing 97 + 18k |
| lens keep-out | V30's 66 points, byte-identical |
| stage datum and seam | `race2_scene`, untouched |
| canopy | none — the frame top never rises above −9.10° |
| floor half-extent | 78.0, against V30's 78.54 and the 75 the centre ray needs |
| grade | `white` 12.0, exposure 0.82, contrast 1.02, saturation 1.06 |

And the controls: `contained_bay_v30`, `horseshoe_arena_v30`,
`stepped_chamber_v30`, `contained_hall*`, `aurora_valley_v26`, V30's four tools
and its own test file and write-up are all **byte-identical to the base**. Every
number in this document is a difference against a render of V30's shipped
profile, so V30 moving would invalidate the comparison.

---

## 4. Part A — the floor

### 4.1 The measurement V30 needed and did not have

`tools/race2_v301_floor.py` is the floor's envelope tool: the same ray grid as
V30's, binned onto the floor plane rather than reduced to radii, plus the
seam-rate arithmetic.

| shot | frames | narrowest | median | widest | range |
|---|---|---|---|---|---|
| `release` | 45 | 18.75 | 26.92 | 35.47 | 84.07 |
| `upper` | 136 | 15.18 | 24.86 | 28.85 | 69.25 |
| `middle` | 74 | 11.87 | 18.26 | 18.86 | 52.42 |
| **`run_in`** | 130 | **7.05** | **10.21** | 16.50 | 27.00 |

| pitch | seams/s | across the narrowest frame | across the sprint's median |
|---|---|---|---|
| **2.38** | **5.06** | 2.96 | 4.29 | ← V30: the grate |
| 9.00 | 1.34 | 0.78 | 1.13 |
| **13.00** | **0.93** | 0.54 | 0.79 | ← V30.1 |
| 18.10 | 0.67 | 0.39 | 0.56 |
| 26.50 | 0.45 | 0.27 | 0.39 |

**The two numbers pull in opposite directions and that is the whole floor
problem.** A pitch fine enough to put several seams across a 7-unit frame puts
five a second through it, and five a second is a pattern the eye tracks instead
of the race. A pitch coarse enough to stay quiet shows at most one seam in the
narrow shots, and a shot with no edge anywhere renders as a smooth gradient —
which is the *other* failure V30 measured, from a 34 × 30 run-out pad that
covered its whole frame.

So the target is a **band**, about 0.4 to 2.0 seams a second, and both ends of
it are failures somebody has already had.

### 4.2 The three treatments

Same architecture, same walls, same practicals, same palette. One section
differs — `deck.plates` — so the comparison is a floor comparison.

| | pitch | seams/s | modules | meshes | triangles | sprint lines/1000 rows |
|---|---|---|---|---|---|---|
| **A** broad slab | 26.50 | 0.45 | 36 | 215 | 68,096 | 3.27 |
| **B** foundation plates | 13.00 | 0.93 | 144 | 323 | 92,720 | 3.73 |
| **C** recessed channel | 18.10 | 0.67 | 63 | 260 | 78,356 | 3.50 |

All three are within 0.03 of each other on near-black, racer separation and
hue, so the choice is made on the image.

**A is too empty.** At 0.45 seams a second the central chase, the switchback
and `sprint_mid` contain no edge anywhere and render as smooth gradients. This
is the gradient failure, reproduced deliberately.

**C is attractive and loses the money shot.** Its two omitted modules read as a
deliberate architectural channel in the chase framings. At an 18.1 pitch the
last four seconds carry too little definition.

**B is selected.** It is the only one that keeps an edge in every framing
without becoming a pattern, and its 144 modules are still 54 fewer plates than
V30's 198.

### 4.3 Large modules, not fine strips — and squareness is half of it

V30's plate is 52 × 2.2: an aspect ratio of **24**. A field of those has one
scale and reads as a grate however wide the gaps are. V30.1's is 12.5 × 12.5.
The tests assert the aspect ratio stays between 0.5 and 2.0.

Sixteen of the 144 modules are `hall_deck_mid`, five L* under the deck,
arranged in **runs of two and three** so the floor carries a few large tonal
blocks rather than a scatter of darker tiles. V30 authored the same
relationship and it never appeared — at specular 0.5 the reflection swamped a
five-point albedo difference.

### 4.4 A seam is a line, not a trench

V30 laid 0.6-thick plates on a base 1.45 below them, so a 0.18 seam opened onto
a surface 0.55 down: an **aspect ratio of 0.33**, which at this grazing angle is
a slot in full shadow. Its own documentation calls the first version of this
"high-contrast corduroy" and records fixing it; the fix reduced the depth and
left the ratio at a third.

`_under` now solves for the depth instead of typing it — the three numbers that
set a joint's profile live in three different fields — and the seam is 0.50
wide by 0.30 deep, a ratio of **1.67**.

### 4.5 Two builder interactions found by the audit

**`terrace` cannot be used with `under`.** Floor B was going to be a stepped
field. `_plates` drops each band of plates beyond `terrace.from`, and the base
slab is a single box at one height — so past r = 56 the lining stands *above*
the plates it lines and the floor renders as bare `hall_deck_dark`. The surface
audit measured **18.24% of the film** against V30's 0.09%, and no frame looked
wrong enough to notice, because a dark floor that is dark everywhere just looks
like a dark floor. The available fix was to deepen the base past the lowest
step, and that is the wrong fix: the base's depth is also the seam depth. A
terraced field needs a terraced base, which is a builder change, so the field
is flat.

**`under.margin` is 2.5, and V30's 6.0 is a trap.** The base is
`span + 2·margin` across while the plates cover `cells · cell`, so the exposed
border is `margin` plus half a pitch. V30's field is 3 × 66 and the border was a
thin line in z; a square field turns the same margin into a ring of bare lining
around the whole floor, at the radius the hook's centre ray lands in.

### 4.6 One new primitive

`environment_stage._plates` gains `skip_x` and `skip_z`: a row or column left
out, so the `under` slab reads as a recessed service channel. **A channel cannot
be made by widening `gap`**, because that widens every joint in the field at
once — a seam is a joint between two present modules and a channel is an absent
one. Same shape as `_deck`'s ring `skip`, six lines, and it warns rather than
cutting a hole when a field has no `under` to line it. Only treatment C uses it.

---

## 5. What the scene actually builds — and what V30 never did

**`environment_stage` refuses an element inside its `clearance` of the racing
line or its `keepout` of the camera path, reports it with `push_warning`, and
`tools/race2_render.py still` did not surface it.**

`tools/race2_v301_stage.py siting` reimplements both guards in Python against
the same data the scene builds them from. Its answers agree exactly with the
scene's own `stage: census` print, which this pass also made visible.

| | pads authored | built | bays authored | built |
|---|---|---|---|---|
| **V30** | 13 | **8** | 2 | **1** |
| V30.1 | 24 | **24** | 2 | **2** |

All five refused V30 pads are warm floor inlays — **five of its nine are not in
the film** — and the sharp part is which five. Three are the ring, missing a
clearance of 13 by 1.0 to 2.5 units. The other two are at (−18, 33) and
(−4, 35): **two of the three inlays V30 sites from the final sprint's own
measured footprint**, the group its documentation introduces with "a practical
that is not in the floor is not in the shot that matters". Two thirds of the fix
for the money shot is absent from it, refused on a 6-unit camera keep-out by 0.7
and 2.5 units.

The sixth is the `sweep` portal — the one place in the room where two large
planes diverge, and the feature V30 describes at length — refused on a keep-out
of 14 at a site 6.6 from the camera path. It has never been in a frame.

**Nothing contradicted any of it**, because the surface audit measures
`lit_hall_warm` at 0.61% either way: four inlays plus the wall slots are enough
to register. Coverage says "is this family visible"; it cannot say "is this
family visible *because the scene built what was authored*". Both instruments
are needed.

### 5.1 Why flush floor art carries clearance 0

The guard exists to stop a tall form standing on the racing line or blotting
the lens, and a flush inlay is neither. That argument is V30's own — its
warm-slot docstring makes it — and then it authored clearance 13 anyway, so the
reasoning never reached the number.

Here it is a proof. `race2_scene` lifts the stage so the floor's top sits
`STAGE_FLOOR_CLEARANCE` = 2.0 **below the lowest point of the racing line**, so
an element whose top is under 2.0 above the floor cannot reach the line
anywhere on the course. The tallest thing in the runway and the practicals is
0.26. **Anything that stands up keeps its guard**, and the `sweep` bay is
*moved* rather than exempted.

### 5.2 The bay's new site is searched, not nudged

Over a 2-unit grid inside the live arc, **154 sites** satisfy all four
constraints at once. The chosen one has the best margins among those the floor
map says the film looks at:

| | value | needs |
|---|---|---|
| at | (−24, −56), r 60.9, bearing 203 | the peak-sector band |
| racing line | 37.0 | 11 |
| camera path | 31.0 | 14 |
| pylon ring | 13.0 | 13 |
| share of the picture | 0.183% | > 0 |

The offset is 56 units from the `sweep` station, which is honest rather than
incidental: this is architecture in the live arc rather than a landmark at a
race node, because on this course the live arc is far from every station. The
anchor stays on `sweep` for the engineering reason the anchor exists — a course
without that station builds no bay, rather than one at the origin.

### 5.3 The floor stack

Every piece of floor art is a slab laid on the deck, so they occlude each other,
and the first build got the order wrong in the one shot that matters: the runway
apron was 0.19 above the deck and the warm inlays 0.13, so a 50 × 26 slab laid
across the whole sprint covered the three assemblies inside it. Measured
consequence: **the sprint's warm coverage fell to 0.087%**, against V30's 0.706%
and against 0.389% for the same floor *without* the runway. A feature added for
the sprint deleted the sprint's warm light.

It is an explicit ordered table now — apron 0.06, inset 0.10, run-out 0.14,
channel 0.20, strip 0.26 — because "how high is this pad" is the wrong question
and "what is under what" is the right one, and only the second is checkable.
`siting` asserts it.

**Everything is above the deck, and that is a constraint rather than a choice.**
The plate field covers the whole floor, so a pad whose top is below the deck is
behind the plates and invisible. A recess in floor B is therefore a darker value
at the same level, not a lower one; floor C is the variant with true recesses.

---

## 6. Part B — the walls

Not one radius, height, arc, thickness or batter moves. What moves is
`pattern`, which is the only field that decides how many separate things a
viewer counts on a wall face — and one palette row, because **no amount of
articulation is visible on a surface with no light on it**. `hall_panel` goes
from #23272E to #434149 and loses its clearcoat: `_moulded` puts a second
specular lobe on top of the first, which on a large flat face is a broad sheen
that flattens exactly the shallow reveals this pass authors.

| band | V30 | V30.1 | runs |
|---|---|---|---|
| near flank | rib slot bay slot rib | panel panel **bay** panel panel | 5 → **3** |
| deep rear | panel bay slot bay panel | panel panel **bay** slot panel | 4 |
| far flank | rib slot panel rib | panel **rib** slot panel | 4 |
| upper | 11 segments, panel/rib alternating | 9 panels, 2 ribs | 5 |

The rule the brief asks for is 2–4 large architectural shapes rather than 30
details, and the way to get them from this builder is to let a form **run**
across several segments: three panels in a row is one broad face, because
nothing interrupts it. The bays get *deeper* rather than more numerous —
`bay_depth` 5.0 → 7.5 and 7.0 → 8.5 — because a recess is read by the shadow in
it, and a shallow wide bay lit from −46° has no shadow in it at all.

The near flank also gains a **shallow stepped plan**: `radius_step` 1.8 on a
4-segment cycle, one reveal across the hook's whole background. V30 used a
radius cycle on its upper band and never on the one the opening looks at.

**The `drum` bay becomes an alcove, and that is where the central chase's black
mass was.** `kind: "backing"` builds exactly one slab — `_bay_form` has no
second branch for it — so a 26 × 17 backing is one flat rectangle, and at 6.8 s
that rectangle is a third of the frame in the room's darkest value.
`kind: "alcove"` runs three more branches of the same builder: a back set behind
the opening, two jambs at the nominal plane, a head in the trim value. Four
large shapes where there was one, for three meshes.

Its depth is bounded from both sides, and the upper bound cost a render.
Too shallow and there is no shadow across the back. **Too deep and the builder
opens a real hole**: the back stands `depth` behind the jamb plane while the
jambs are only `thickness` deep, so the sides of the recess are open above and
below, and from the central chase's angle the lens looks straight through into
the room's darkness. At depth 4.5 that moment's near-black went from V30's
0.60% to **2.52%**, and on the void map it is a black *tear* rather than a dark
surface — worse than the slab it replaced. At 2.2 with a 4.6 jamb it is 1.09%.

---

## 7. Part C — the material palette

No new palette key. Eleven V27 rows plus V30's twelfth, re-tuned.

| key | V30 albedo | V30.1 albedo | specular | why |
|---|---|---|---|---|
| `hall_deck` | #443A2C | **#474549** | **0.10** | a real graphite at the specular that lets it stay one |
| `hall_deck_mid` | #3E3527 | #434148 | 0.10 | five L* under the deck: a tonal block, not a second material |
| `hall_deck_dark` | #322C22 | #363439 | 0.08 | a seam describes an edge; it does not cut a hole |
| `hall_panel` | #302C27 | #434149 | 0.12 | lifted so articulation is visible; clearcoat off |
| `hall_panel_dark` | #1D1A16 | #302E34 | 0.05 | dark *paint*, not absence — §6 |
| `hall_rib` | #3B3730 | #514F55 | 0.26 | the one surface allowed a real highlight |
| `hall_trim` | #615C52 | #766F68 | 0.22 | the light value that describes an edge |
| `hall_grate` | #3D362B | #4C4945 | 0.14 | the machine's foundation, four points of warmth |
| `lit_hall_warm` | #FF9A47 @ 0.62 | unchanged | — | V30's energy was right; only *where* changed |
| `lit_hall_cool` | #8FB6D2 @ 0.44 | #B9C6CE @ 0.40 | — | |

**The albedo is very slightly cool and the render is very slightly warm, and
that is the pre-compensation that is actually needed.** V30's was 60 points of
hue in the wrong direction for the wrong reason; this is four in the right one.
An earlier V30.1 build at #5C554C measured blue/red **0.83** and read as olive
sand on the sheet — the cast inverted, not removed.

**The rule that emerged, and it caught three separate surfaces:** *a surface's
allowed chroma is set by its screen area, not by its material story.* The first
`hall_grate` was #635B4F, defensible on a swatch and an olive block at 10–25% of
three frames. The first warm-inlay shoulder was `hall_trim`, correct detailing
and a pale bar brighter than anything but the running surface in the money shot.
The first runway insets were `hall_deck_dark`, eighteen L* under the deck where
five was the brief.

### 7.1 The fifth world light

V30's note says "all four lights off the blue", and it moves four.
`contained_base` authors **five**. `WorldBounce` — #3C5878, energy 0.55, the
strongest remaining blue in the room and higher-energy than either light V30
dimmed — is inherited untouched through `environment_profile.merge`, which is a
deep merge, so a light a child never names survives into it.

It is **neutralised, not removed**: it points up at +24°, so it lights the
downward and side faces no other light in the rig reaches, and deleting it would
take the underside of every reveal, seam and channel to black — which is the
surface this pass is authoring. On the final sprint neutralising it changes
nothing to a tenth of a level, which is itself the reason to distrust any story
about what colours that shot.

### 7.2 A claim about the sky, corrected

V30 reasons at length that the sky is "chosen as a light rather than as a
picture" because it supplies ambient and, through `reflected_light_source`,
every specular reflection in the room. The first half is true. Setting this sky
to **pure red at full energy**, with every light deleted, moves the final
sprint's lit floor from RGB(23.0, 98.2, 108.0) to RGB(23.1, 98.2, 108.0). The
sky contributes nothing to this picture through any path. It is left where V30
put it, and no claim is made about what it does.

---

## 8. Part D — the warm practicals

**The change is a shape change, not a brightness change.** V30's energy of 0.62
was right — at 1.9 a strip clips to paper white and stops being warm. What
makes a light read as part of a building is that it sits in a recess whose
housing is a different value from the surface around it, so each assembly is
two parts: a `hall_deck_dark` channel 1.8 wide, and a 0.6-wide `lit_hall_warm`
strip inside it. Eight of them, all eight in the film, against V30's four.

Warmth reaches the wall two ways — a `slot` in a band's rhythm and the strip
inside a `bay` — on three of the four bands.

Two things were tried and are recorded because each is a rule:

**The `hall_trim` shoulder.** Real recessed fittings have a bright lip, and at
17–26 units long in this film it is a pale bar across the money shot. Dropped.

**The channel at 3.2 wide.** Nine channels 17 units long at that width, all in
the near ground of a chase shot, put `hall_deck_dark` at 39% of the early
chase on its own. At 1.8 it is three times the strip — the proportion a real
fitting has — instead of a dark band with a light in it.

---

## 9. Part E — the final sprint

### 9.1 The sprint is two shots inside one take

Over its 6.47 s the centre ray sweeps a wide arc — (−7, 6) out to (17, 0) and
back through (15, 11) — and then from about **t = 15.1 it settles and barely
moves again**: (−13, 20), (−17, 24), (−16, 25), (−14, 26), (−12, 27). The last
four seconds of the film are one framing, and it is the framing the winner
crosses in. V30 treated the sprint as one field; the money shot is the smaller
one inside it.

| | x | z | centre |
|---|---|---|---|
| the sprint's floor field | −34 … 38 | −34 … 34 | (−5, 16) |
| **the money shot's** | **−20 … −8** | **16 … 36** | **(−14, 26)** |

**And the machine's own left edge is at x = −13.3**, with the racing line never
passing z = 26. So the floor the last four seconds can see that nothing is
standing on is a **6-unit strip** at x < −14, plus the band past z = 28.

### 9.2 Three attempts, and the finding under all of them

**Attempt 1** put the side insets on a 30-wide foundation band's outer edges, at
x = −27 and +1. The sprint's frame is 7.05 to 16.50 units wide at the floor, so
both edges were outside the picture and the warm coverage *fell* to 0.265%.

**Attempt 2** moved them into the money box and made them long — 26 units, two
crossing — and produced the picture the brief explicitly forbids: two bright
orange bars across the winner frame, a glowing neon runway, at 2.316% coverage,
four times V30's, every point of it in the wrong place.

**Attempt 3** dropped the broad apron. The surface audit had measured it at
**89.6% of the winner frame**: a 50 × 26 slab is not a zone within a shot that
sees a 12 × 20 patch, it *is* the shot — and with the whole frame one value the
13-unit module rhythm underneath it was gone, which is why that frame rendered
flat. It is V30's own 34 × 30 run-out pad, rebuilt at a different size for a
different reason.

**The finding is one number.** *Any* element long enough to read as a line in a
6-unit-wide strip spans the frame, so in this shot a long element cannot be an
accent — it is either invisible or it is the subject.

### 9.3 What the runway is

Edges rather than an area, each sited against a measurement:

- **one side inset**, 4.5 wide at x = −19.5 running z 12–40, in the free strip,
  running the direction the shot travels. The brief asks for two and the
  machine is in the way of the second: there is no corresponding free strip on
  the other side.
- **a destination band** at z = 33, 46 × 5, lying across the picture nine units
  behind the finish. The camera path passes 1.0 from it, which is exactly why
  it is flush: at a fifth of a unit high it is under the lens, not in it.
- **the run-out's apron**, 22 × 12 at (−24, 30), offset into the free strip.
- **one short warm strip**, 14 units in a 20-deep patch at x = −18, laid along
  the shot rather than across it. It cannot become a bar across the picture
  because it is shorter than the patch it is in.

### 9.4 Part F — the run-out

V30 deliberately left it bare and listed the absence as a weakness: "correct for
the frame, wrong for the one station the film ends on". Its reason was that a
pad sized to the station covered the frame — true of a 34 × 30 pad laid *under*
the station on a floor whose only other content was a seam every quarter second.
Against 13-unit modules it no longer holds: the apron is 22 × 12, offset into
the free strip rather than centred on the station, and one shape among several
of its own scale. A fifth station kerb is added at the run-out for the same
reason.

---

## 10. The measurements

Ten moments, camera A, five worlds, the same renderer on the same frames.
Coverage is taken against a per-world silhouette matte; environment coverage is
**93.147% in both worlds**, which is the check that the geometry is identical.

| | V30 | **V30.1** | note |
|---|---|---|---|
| near-black, film | 0.208% | 0.302% | |
| near-black, final sprint | 0.037% | 0.072% | |
| room mean luma | 46.3 | **42.0** | darker |
| room mean luma, sprint | 57.9 | **44.7** | |
| **racer − room** | 87.9 | **91.8** | more readable |
| **racer − room, sprint** | 80.4 | **92.7** | +12.2 |
| machine − room | 153.0 | **157.2** | |
| warm practical coverage | 0.565% | **1.187%** | 2.1× |
| warm coverage, sprint | 0.706% | **0.937%** | 1.3× |
| blue/red, V30's measure | 1.181 | 1.088 | |
| **blue/red, bright quartile** | 1.417 | **0.994** | neutral |
| **chroma, bright quartile** | 0.371 | **0.202** | 1.8× down |
| edge density, film | 5.80% | **1.72%** | 3.4× down |
| edge density, sprint | 5.44% | **1.26%** | 4.3× down |
| dark lines / 1000 rows, film | 9.19 | **6.41** | |
| dark lines / 1000 rows, sprint | 7.46 | **3.27** | 2.3× down |
| line amplitude, sprint | 2.80 | 2.45 | shallower as well as fewer |
| module pitch | 2.38 | **13.00** | 5.5× |
| **seams a second** | **5.06** | **0.93** | |
| meshes | 367 | **326** | |
| triangles | 102,752 | **93,404** | −9.1% |
| ms/frame @1080×1920 | 196 | **190** | |
| encoded film, CRF 17 | 18.5 MB | **12.0 MB** | −35% |

The encode size is not a target and is worth recording anyway: at identical
settings on identical motion, a third less bitrate is an independent statement
that the picture carries far less high-frequency detail.

### 10.1 Over all 1150 frames rather than ten of them

| | V30 | V30.1 |
|---|---|---|
| frames | 1150 | 1150 |
| near-black, mean | 0.329% | **0.642%** |
| near-black, 99th percentile | 5.28% | 6.90% |
| near-black, worst frame | 8.70% | **10.77%** |
| frames above 2% | 23 | **132** |
| frames above 10% | 0 | **1** |
| frames above 25% | 0 | 0 |
| dark lines, mean | 11.62 | **9.24** |
| dark lines, worst | 28.92 | **22.39** |

| shot | frames | V30 near | V30.1 near | V30 lines | V30.1 lines |
|---|---|---|---|---|---|
| `release` | 132 | 1.300% | 1.963% | 14.28 | 12.64 |
| `upper` | 408 | 0.387% | 1.035% | 13.03 | 11.28 |
| `middle` | 219 | 0.044% | 0.029% | 8.77 | 6.75 |
| **`run_in`** | **391** | 0.101% | **0.129%** | 10.84 | **7.36** |

**This is the one measured regression and it is not the environment.** The worst
frames are the opening half second and one moment at t = 8.15, and on the void
map their near-black is the **machine's own shadowed undersides** — which
darkened because the room did. Three environment levers were swept against it:

| lever | change | worst frame | racer separation |
|---|---|---|---|
| baseline | — | 10.76% | 82.7 |
| `ambient_energy` | 0.68 → 1.00 (+47%) | 10.54% | 83.0 |
| `WorldFill` | 0.30 → 0.60 (doubled) | 10.72% | 81.6 |
| `WorldWarm` +50%, `WorldFill` +40% | | 10.61% | 80.3 |

Each moves it by **under 0.2 percentage points** while costing racer
separation. The pixels are machine geometry in shadow and the machine is locked,
so this is unreachable from an environment profile. It passes the brief's guard
by a wide margin — 0.642% against 2% over the film, 0.129% against 2% in the
sprint — and it is the price of the darker room that bought the +3.9 and +12.2
in racer separation above.

### 10.2 Surface coverage (Part W)

Marker render, flat unshaded albedo per family, linear tonemap at unit white.

| family | V30 | V30.1 | frames | peak | at |
|---|---|---|---|---|---|
| `hall_deck` | 43.47% | **32.80%** | 10/10 | 49.97% | sprint_early |
| `hall_deck_mid` | 13.64% | 15.94% | 9/10 | 47.07% | winner |
| `hall_panel` | 11.19% | 15.78% | 8/10 | 53.85% | hook |
| `hall_grate` | 12.14% | 15.75% | 9/10 | 47.60% | sprint_mid |
| `hall_trim` | 3.46% | 5.44% | 8/10 | 15.47% | hook |
| `hall_deck_dark` | 0.09% | 4.11% | 10/10 | 8.75% | winner |
| `hall_rib` | 2.66% | 1.44% | 8/10 | 4.14% | early_chase |
| `lit_hall_warm` | 0.61% | 0.86% | 8/10 | 2.59% | winner |
| `hall_panel_dark` | 5.20% | 0.32% | 3/10 | 1.15% | late_mechanism |
| `lit_hall_cool` | 0.17% | 0.19% | 5/10 | 1.22% | sprint_early |

**Authored families seen: 10 of 10. Authored but unseen: 0.** `hall_glass` and
`hall_beam` are authored by neither, for V30's reasons — the frame top never
rises above −9.10°.

Two rows are the pass in miniature. `hall_panel_dark` falls from 5.20% to 0.32%
because the flat black slab became an alcove interior. `hall_deck_dark` rises
from 0.09% to 4.11% because the seams are now wide enough to see — and the two
builds where it reached 18–20% are §4.5.

---

## 11. Shot by shot

**Hook (0.00–2.23).** The striped floor patch that filled the lower right is a
broad clean surface. `hall_panel` peaks here at 53.85% and now carries a
stepped plan and a deep bay rather than five different kinds. The title area is
clean and dark in both; no practical behind it. Near-black 1.10% → 1.40%.

**Early race (2.23–5.20).** The orange mechanism reads against a calm floor
instead of a moving grate. Dark lines per 1000 rows 20.14 → 14.10.

**Mid race (5.20–12.68).** Where the grate was most noticeable and where the
largest improvement is. The central chase's black mass is gone (near-black
0.60% → 1.09%, and a legible wall where a hole was); the switchback's lines fall
2.80 → 0.93; `late_mechanism` 7.09 → 1.01.

**Final sprint (12.68–19.15).** 391 frames, no cut. Edge density 5.44% → 1.26%,
lines 7.46 → 3.27 at a lower amplitude, racer separation 80.4 → 92.7, warm
0.706% → 0.937%. The winner frame's lines fall 11.19 → 2.80.

---

## 12. Phone review, 270×480

From `sheet_270.png` and `race2_v301_phone_compare.mp4`, and the strip through
the sprint is where it is clearest: in V30 the floor pattern is the strongest
thing in **every** frame of the take.

| question | answer |
|---|---|
| do I notice the racers first? | yes, and more than in V30 — separation 91.8 vs 87.9 |
| does the floor become visual noise? | no. It was noise in V30 from ~6 s |
| does the room still have depth? | yes — the radii are V30's, 4.88× image-speed spread |
| does the environment look premium? | engineered graphite slab, not a grate |
| can I continuously track my colour? | yes, in all ten moments |

---

## 13. The art-direction questions (Part X)

1. **Does the floor still look like a grate?** No. 5.06 seams a second → 0.93,
   edge density 5.80% → 1.72%, and the module aspect ratio 24 → 1.0.
2. **Does the stage look more expensive?** Yes. Large engineered slabs in a
   neutral graphite, at bright-quartile chroma 0.202 against 0.371.
3. **Do the walls look designed rather than blocked out?** Better, not solved.
   Three broad faces per band with one deep bay, a stepped plan on the band the
   hook looks at, and the value lifted so the articulation is lit. It is still
   a wall the lens only ever sees the base of.
4. **Are the warm practicals integrated?** Yes — each sits in a dark channel
   three times its width, and all eight are in the film against V30's four.
5. **Does the final sprint feel purpose-built?** Moderately. A side inset
   running with the shot, a destination band behind the finish, an apron where
   the machine ends. It is still a floor rather than a set, for V30's geometric
   reason, and §9.2 is the record of what the shot refuses.
6. **Does the environment stay secondary?** Yes, and more than V30: racers 91.8
   above the room, machine 157.2.
7. **Is it less blue/navy?** Yes, decisively. The teal was a specular term, and
   where the eye reads hue the room is now neutral (blue/red 0.994).
8. **Is there enough depth?** Yes; the radii are untouched.
9. **Clean without being empty?** At the selected pitch yes. Treatment A is the
   measured demonstration of what "empty" looks like.
10. **Would country marbles work here?** Yes. The room carries no hue of its
    own.
11. **Could another race use this stage?** Yes, after re-running the envelope
    and floor tools. Nothing is seeded on hero seed 8.
12. **Does it look like a reusable channel environment?** Yes — one profile,
    twelve existing palette keys, no new framework.

---

## 14. Remaining weaknesses

1. **Near-black over the film doubles**, 0.329% → 0.642%, with 132 frames above
   2% against 23 and one frame at 10.77%. Fully diagnosed (§10.1): it is the
   machine's own shadowed geometry, three environment levers are ineffective
   against it, and it is the price of the readability gain.
2. **The sprint is still a floor, not a set.** Unchanged from V30, and §9
   explains why it is geometric.
3. **One warm strip reads as a bright line** in the upper-left of the frame at
   about t = 15.6. It is at the frame edge and lasts about a second.
4. **`hall_panel_dark` is thin** — 0.32%, 3 of 10 frames — a consequence of the
   black slab becoming an alcove interior. Authored, accepted and seen, so it
   passes Part I, but only just.
5. **`lit_hall_cool` is in 5 of 10 frames at 0.19%.** Better than V30's 2 of 10;
   still the thinnest authored family.
6. **`hall_grate` is 15.75% of the film** and peaks near 48%. It is close to the
   deck in value so it does not read as a separate object, but it is a lot of
   one surface.
7. **A terraced plate field is not available** without a builder change (§4.5).
8. **Treatments A and C are compared at ten moments**, not frame by frame. Only
   the selected floor has the full-film measurement.

---

## 15. Should environment development stop here?

**Yes.** The brief's stop condition is met: a premium coherent floor with no
repetitive grate feeling, refined low-frequency walls, warm practicals let into
the architecture, a final sprint with a measured runway language, better racer
readability than V30 on every framing, and a phone appearance where the racers
are the first thing seen.

Three further arguments for stopping:

- **The headline defects are fixed at their mechanism, not tuned.** The grate
  was a seam rate nobody had computed and the teal was an unauthored specular
  default. Both are now measured quantities with tools that report them.
- **The residual weaknesses are not environment problems.** The largest is the
  machine's own shadow side, which three environment levers cannot move. The
  second is that the final sprint has no far field, which is a camera fact.
- **The stage is cheaper than what it replaces** — 326 meshes against 367, 9%
  fewer triangles — so there is no performance debt to work off.

What a later pass should *not* do is reopen the tonemapper. V30's sweep is
sound: every tonemap that reduces the cast also costs the racers their candy,
and the cast is now gone without touching it.

---

## 16. Where everything is

| | |
|---|---|
| production profile | `godot/.../profiles/contained_bay_v301.json` |
| floor treatments | `contained_bay_v301{a,b,c}.json` |
| new deck fields | `environment_stage.gd` — `_plates`, `skip_x` / `skip_z` |
| profile writer + siting check | `tools/race2_v301_stage.py` |
| floor envelope | `tools/race2_v301_floor.py` |
| review + clips + phone | `tools/race2_v301_review.py` |
| surface audit | `tools/race2_v301_surfaces.py` |
| evidence | `docs/validation/race2/v301_stage/` |
| films | `exports/race2_v301_stage/` |
| tests | `tests/test_race2_v301_stage.py` |

`output/` and `exports/` are not in git, per this repository's convention.

| deliverable | path |
|---|---|
| V30.1 full film | `exports/race2_v301_stage/race2_v301_v301.mp4` |
| V30 control | `exports/race2_v301_stage/race2_v301_v30.mp4` |
| side by side | `exports/race2_v301_stage/race2_v301_compare.mp4` |
| phone pair | `race2_v301_v30_phone.mp4`, `race2_v301_v301_phone.mp4` |
| phone side by side | `race2_v301_stage/race2_v301_phone_compare.mp4` |
| contact sheets | `docs/validation/race2/v301_stage/sheet_{135,270}.png` |

### 16.1 Tests

`tests/test_race2_v301_stage.py` is **44 tests in five groups**: the locks (the
hero race, camera A's four shots and its 6.47 s sprint with no frame missing,
that no physics/camera/course module moved, and that V30, V29 and V26 are
byte-identical to the base along with V30's tools, tests and write-up); the
architecture unchanged (wall radii, arcs, pylon ring and lens keep-out checked
against V30's own profile, no canopy, no ring, the floor's reach, the seam); what
the scene builds (nothing refused, nothing buried, the flush-clearance proof,
and V30's own five refused pads and one refused bay asserted as historical
fact); the measurements (hue where the eye reads it, racer separation not
regressing, the near-black guard over 1150 frames, warm coverage, no unseen
family, the floor's own value dominant, cost); and the floor frequency (the seam
rate inside its band, the variants spanning it, a seam wider than it is deep,
the module aspect ratio, and the wall's run count).

The selection covering this branch — race2, environment, v23, v26, v27, v29,
v30 — is **664 passed, 18 skipped, 0 failed**. The whole suite is **2788
passed, 6 failed, 338 skipped**; all six failures are in
`test_sloped_v251_world.py` and `test_sloped_v252_world.py` and all six are the
same missing Race #1 artefact, `output/sloped_race_v1/cameras_v221_5432.json`,
which is not in git. V30's write-up records the same failures for the same
reason.

### 16.2 One shared tool changed

`tools/race2_render.py` prints `stage:` and `environment_stage:` lines from the
scene as well as the five prefixes it already printed. That is one census line
per render, and its absence is what let V30 ship a profile whose `sweep` portal
and five warm inlays were silently rejected.
