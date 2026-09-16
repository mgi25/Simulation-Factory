# V31.1: the track surface — what the viewer is actually looking at

**Branch** `v311-track-visibility-polish`, from
`origin/v31-race-readability-camera-track` at `202996e`.
**Scope** the channel's `StandardMaterial3D`. Nothing else. No physics, no
course, no collision, no camera, no environment, no light, no grade, no racer,
no overlay. `tests/test_race2_v311_track.py::test_the_branch_changes_only_render_and_measurement`
asserts the whole diff against the base by filename, so the scope is a test
rather than a claim.

---

## 1. The problem, as the brief states it

> bright outer rails, coloured marbles, dark environment — but the actual
> raceway surface becomes difficult to trace. The rail survives, the road
> disappears.

That description is exactly right about the picture and it names the wrong
cause. The brief's model is that the deck is *too dark and too blue* and is
sinking into a dark graphite room. Two measurements say otherwise, and both of
them are counts of pixels rather than opinions about them.

---

## 2. What the segmentation found

`--track=mask` and `--track=bands` paint the scene as flat unshaded classes with
fog, tonemapping, grade and MSAA switched off, so a pixel's class is a fact
about the frame. One mask set serves every candidate, because no variant moves
a vertex.

### 2.1 The deck is not dark. It is not there.

Screen coverage on the thirteen sampled moments, RB camera, `contained_bay_v301`:

| moment | t | cradle | lip | wall face | crown | channel | racers |
|---|---|---|---|---|---|---|---|
| grid | 0.35 | **0.375** | 0.033 | 0.282 | 0.030 | 0.719 | 0.000 |
| hook | 1.20 | 0.214 | 0.542 | 4.461 | 0.468 | 5.685 | 2.627 |
| drum | 3.20 | **0.000** | 0.445 | 3.437 | 0.347 | 4.229 | 1.185 |
| sweep | 5.20 | 0.001 | 0.345 | 2.715 | 0.279 | 3.341 | 0.581 |
| chase | 6.80 | 0.066 | 0.427 | 3.081 | 0.293 | 3.866 | 0.371 |
| switchback | 8.40 | 0.001 | 0.073 | 0.815 | 0.122 | 1.011 | 0.370 |
| gorge | 9.60 | **0.000** | 0.372 | 2.861 | 0.294 | 3.527 | 0.690 |
| sparse | 10.60 | **0.000** | 0.406 | 3.099 | 0.309 | 3.813 | 0.750 |
| late_mech | 12.20 | **0.000** | 0.136 | 1.380 | 0.185 | 1.702 | 0.450 |
| sprint_in | 13.60 | **0.000** | 0.331 | 2.500 | 0.247 | 3.077 | 0.151 |
| comeback | 15.40 | **0.000** | 0.260 | 2.067 | 0.218 | 2.545 | 0.430 |
| line | 16.20 | **0.000** | 0.098 | 0.751 | 0.074 | 0.923 | 0.431 |
| runout | 18.00 | **0.000** | 0.079 | 0.619 | 0.063 | 0.762 | 1.333 |

**The cradle — the surface a marble rolls on — covers 0.000% of the frame on
eight of thirteen moments and never more than 0.066% of a racing one.** The
brief's "the road disappears" is not a figure of speech and not a value
problem: there is no road pixel to make brighter.

What the viewer sees instead is the **inner face of the guard wall**, which
carries **78–81% of every channel pixel** on every racing frame, with the crown
and lip splitting most of the rest.

The mechanism is geometric and it belongs to the *camera against the course*
rather than to either one alone. The switchyard descends at about 0.65 units per
unit of plan — 33 degrees — and V31's RB camera sits at a measured depression of
38.9 degrees. The lens is therefore about **six degrees above the channel's own
plane**, and at six degrees a 0.68-unit guard hides 6.5 units of cradle behind
it. The cradle is never more than 3.76 units wide.

### 2.2 The visible band is not dark and not blue

Measured over the pixels the mask selects, in the delivered V31 render:

| band | where it is | share of channel | L* | mean RGB |
|---|---|---|---|---|
| crown | the top 0.05 of the guard | ~8% | **87.7** | — |
| wall face | 0.53 down to −0.02 | **~80%** | **86.1** | (220, 219, 217) |
| lip | the curve into the cradle | ~10% | 68.5 | — |
| cradle | the running surface | ~0% | 33.5 | — |

The room it sits against measures **L\* 14–19**. The separation is **ΔL\* 65,
ΔE 65**. The rendered cast is **R−B = +0.7** — dead neutral, very slightly warm
at some moments, cool at exactly one (5.20 s, −11.8).

So: there is no blue cast to remove, there is no darkness to lift, and the
raceway is separated from its environment by twenty-five times a just-noticeable
difference. **Part D's target was already met before this pass started, and the
premise of Part E was false.**

### 2.3 What is actually wrong

Two things, and neither is the one in the brief.

**The track is the brightest object in the frame.** The racers measure L* 34–72.
The channel measures 82. The visual hierarchy the brief asks for — racers first,
track second — is **inverted by 27.7 L\***.

**The rail has no edge.** The crown and the wall face are the two bands the
camera actually sees, and across the whole film they sit **1.63 L\* apart** —
and at 12.20 s the crown is *darker* than the face it caps, by 0.9. A surface
whose parts are all one value has no form, and a form with no internal value
change reads as a **line**, not a plane. That is precisely the "marbles moving
between rails" the brief describes, and it is a property of the material rather
than of the framing.

The distribution says the same thing: over the visible band, p25 to p95 spans
86 to 90 on a typical chase frame.

---

## 3. Camera versus material — and what Part E actually found

V31 fixed **where the lens points**. This pass could only change **what the
surface does with the light that reaches it**. Section 2.1 is the line between
them: a material cannot show a viewer a surface the near rail is standing in
front of, and no amount of albedo will put the cradle on screen.

So the question became: of the fields the brief names in Part E — albedo,
roughness, metallic, specular — which one is the band on screen actually
sensitive to? `--track-probe=` moves exactly one at a time over the control, and
the answer is blunt.

| probe | band L* | band σ L* | R−B |
|---|---|---|---|
| **control** (`#D2D8DE`, rough 0.20, clearcoat 0.95/0.04) | 85.42 | 8.63 | 1.2 |
| albedo `#9AA0A6` | **71.49** | 9.88 | 0.9 |
| albedo `#EFEFEC` | **88.92** | 7.89 | 6.2 |
| roughness 0.55 | 86.54 | 7.26 | 1.6 |
| roughness 0.80 | 87.26 | 6.48 | 1.8 |
| **specular 0.20** | **85.42** | **8.63** | **1.2** |
| **specular 0.00** | **85.42** | **8.63** | **1.2** |
| clearcoat 0.0 | 86.12 | 8.25 | 1.1 |
| metallic 0.60 | 65.44 | 9.90 | 3.6 |

**`metallic_specular` is bit-for-bit inert.** At 0.50, 0.20 and 0.00 the frames
are identical, not merely close. `clearcoat = 0` — removing a 0.95 lobe
entirely — moves the band by 0.7 L*. Roughness across its whole useful range
moves it by under two.

The reason is the room, and it is worth writing down because it will be true of
every pass in this environment: `contained_bay_v301`'s sky is `#0C0B0A`, its key
carries `specular 0.14`, and **every other light in the rig carries specular
0.0**. There is no sky to mirror and almost no specular to return, so a channel
with a mirror finish and a channel with a matte one are the same channel. **The
surface is pure diffuse albedo, whatever its gloss fields say.**

That also explains the flatness. Sweeping the albedo down a ladder:

| albedo | band L* | p5 | p95 | spread | racers − track |
|---|---|---|---|---|---|
| `#D2D8DE` (V31) | 85.42 | 71.7 | 89.7 | 18.0 | **−21.8** |
| `#C9C7C2` | 82.40 | 67.0 | 87.2 | 20.2 | −18.9 |
| `#BBB9B4` | 79.20 | 62.4 | 84.5 | 22.1 | −15.8 |
| `#ADABA6` | 75.37 | 57.3 | 81.3 | 24.0 | −12.1 |
| `#9F9D98` | 70.83 | 51.6 | 77.2 | 25.6 | −7.7 |
| `#918F8A` | 65.47 | 45.6 | 72.3 | 26.7 | −2.4 |

**Every step down in value buys a step up in the band's own internal spread.**
The channel is sitting on the shoulder of the ACES curve (`white` 12.0,
`exposure` 0.82), where a two-to-one change in incoming light arrives as two
L*. Lowering the albedo is not "making it darker" — it is moving the surface
back onto the part of the curve that can still show its shape.

**So the cause is: a light diffuse surface parked on the tone curve's shoulder,
with no cross-section value structure, seen at grazing incidence in a room that
returns no specular.** Albedo is the only live lever, and how albedo is
*distributed across the section* is the only lever that can put an edge back.

---

## 4. Variant A — light pearl

One neutral value across the whole channel, satin rather than lacquer. The
conservative candidate, and also the ceiling of what a single uniform value can
do.

```
albedo   #BEC1C4     roughness 0.42     clearcoat 0.55 / 0.10
```

Three decisions:

**Value settled, not lifted.** The brief asks to lift the deck; the measurement
asks to settle the band that is on screen. `#BEC1C4` lands the channel at
L* 79.3 — a light grey rather than a white, still 62 points clear of the room,
and 2.8 points closer to the racers.

**Neutral in the render, which is not neutral in the albedo.** This is the
finding that cost the most to learn. V31's `#D2D8DE` is 210/216/222 — twelve
points of blue over red — and it *renders* at R−B = +0.7. The room adds about
twelve bytes of red-minus-blue to anything put in front of it: `WorldWarm` is
`#FFC694`, the bay practicals are warmer again. **The albedo's coolness is
load-bearing.** Taking it out — Part D read literally — overshot to R−B = +11.7,
a visibly warm track in a cool room. `#BEC1C4` keeps six points of the coolness
and renders at **+4.3**: Part D's "neutral or slightly warm-neutral", measured
where Part D says to measure it.

**Roughness and clearcoat moved with no illusions.** Section 3 says they buy
under two L*. They are kept at 0.42 and a narrowed 0.55/0.10 because the 0.04
clearcoat lobe lays a hard white streak across a banked pan, which is a real
defect — not because they change the value.

---

## 5. Variant B — pearl plus an inner value break

A's material with the albedo **distributed across the section** by a 1-D
texture in `u`.

The mechanism is the only one available: the channel is **one swept strip per
run with one `material_override`**, so deck and rail are the same mesh and a
second material would mean new geometry, which Part B forbids outright. But
`race2_scene._strip_mesh` already writes `u = column / (section_points − 1)`,
walked from the west guard top across the cradle to the east one. At Race #2's
21-point section that is an exact address for every band, and a texture across
`u` separates them inside one material with the vertices untouched.

The profile, as gains on A's albedo:

| band | `side` | gain | what it is |
|---|---|---|---|
| cradle | 0.50 → 0.33 | **1.35** | the running surface, lifted |
| lip | 0.27 | **0.55** | a shadow line at the foot of the rail |
| wall base | 0.24 | 0.70 | |
| wall top | 0.10 | 1.14 | a gradient **up the face** — the thickness cue |
| crown | 0.055 → 0.00 | **1.34** | the brighter silver edge |

Two things make this a material hierarchy rather than a painted stripe, and both
are asserted in `test_variant_b_break_is_a_ramp_and_not_a_stripe`:

**The section has exactly one corner.** Walking `capped_profile(2.0)` and
measuring the turn at every point gives **53.7 degrees at the cradle edge**
(u 0.30 and 0.70) and **under 8 degrees everywhere else**. The first draft of
this profile assumed four corners — a lip fillet, a bevelled crown — and was
wrong: the guard is one smooth curve from the running surface to its top. So the
rule is that a ramp may be steep **only** where it sits on that one corner. The
cradle-to-lip drop is the steep one and it is centred on u 0.30. Everywhere else
the ramp must be gentle enough that a whole delivery pixel sees under three L*
of change, which the long climb up the face satisfies with room to spare.

**The gradient, not the highlight, is what survives the phone.** A crown
highlight alone is about four pixels on the 1080 frame and one at 270. A
gradient over the whole face is a thickness cue at any size, and it is what
makes B the only candidate that changes the read in the 270×480 sheet.

---

## 6. Variant C — pearl plus roughness and specular control

Part E's hypothesis, built and rendered rather than argued away: A's value with
the gloss chain at the matte end — roughness 0.75, dielectric F0 down to 0.25,
clearcoat off entirely.

It is kept even though section 3 already answered the question, for the reason
V31 kept RC: a candidate that shows the trade turning over is worth more than a
third good one. The measured result:

- **C differs from A by 2.0 L\*** and from the control by 0.7.
- **C is the flattest candidate in the set.** Its band spread is 12.06 against
  A's 14.67 and the control's 15.27.

Roughness on a diffuse-only surface takes modulation away rather than adding
it. **The reflection response is not a lever in this room**, and C is the proof
in motion.

---

## 7. The image-space diagnostics

Every number in this document is measured over pixels a mask selected. Four
diagnostic renders exist and none of them reaches a delivered frame:

| mode | what it paints |
|---|---|
| `--track=mask` | deck, rail, structure, station, actuator, racer, room |
| `--track=bands` | cradle, lip, wall, crown; everything else black |
| `--track=racers` | racer `i` as `Color(i/(n−1), 1, 0)`; everything else black |
| `--track-probe=` | one material field at a time over any variant |

**Two instrument bugs were found and fixed, and both would have produced a
confident wrong answer.**

1. `--track=racers` originally let the channel fall through to the deck/rail
   mask, whose rail is pure green — which is also racer 0's class colour. Every
   rail pixel in the film joined racer 0, and the weakest-separation guard
   returned a flat **0.00 ΔE for all four candidates**: a guard that could not
   fail.
2. The racers were first labelled by k-means in `ab`. On the 6.80 s chase, where
   the racers are 0.37% of the frame, eight clusters over three visible marbles
   split one racer into four and swung the "weakest separation" from 16.7 to 8.6
   between two candidates whose racers are **identically lit**. The renderer
   labels them now, and the classifier reads the eight distinct red levels back
   in sorted order — which survives any transfer curve the pipeline might apply.

### The material-only lock, and why it is an amplitude and not a count

For every variant and moment, the frame is compared with the control **outside**
the channel mask. The expectation was exactly zero. It is not, and the reason is
a property of the instrument: the masks are the only frames in this branch drawn
**without MSAA**, and the channel is a thin ribbon receding the length of the
picture, so its silhouette is aliased across about 5% of the frame. Every one of
those pixels is part channel and part room in a 4×-resolved render and
legitimately moves when the channel does.

So the count is not the measurement — the amplitude is:

| | A | B | C |
|---|---|---|---|
| max off-track byte change, 1 px dilation | 17 | 29 | **46** |
| share of off-track pixels moving > 8 of 255 | 0.0000% | 0.0003% | 0.0004% |

The worst case is the 8.40 s switchback, where the channel is at its smallest
(1.011% of frame) and thinnest — the aliasing case — and it is **70 pixels of
2.07 million**. Two renders of the *same* material differ on 0.002% of pixels by
one byte, so this is within a hair of the floor.

### The V31 control reproduces byte for byte

Rendered on a detached worktree at the base commit `202996e` and again on this
branch with no `--track=`, against the same camera track, replay, geometry and
environment: **all four sampled frames are byte-identical**, SHA-256 for
SHA-256. That is what `channel()` returning the palette's own object rather than
a duplicate buys, and it is the answer to "is the historical V31 control
reproducible".

One caveat, and it cost an hour to find. The first comparison came back
*different* — one byte on 0.0127% of pixels at 3.20 s — and the cause was not
the branch. The two renders had been given **different `--at` lists**: four
times against thirteen. Three consecutive renders on the base with the same list
are byte-identical to each other, and so are base-against-branch once the lists
match. This is the same `--at` batching effect V27 recorded; it is a property of
the renderer's warm-up, it predates this branch, and **a reproduction check that
does not hold the `--at` list fixed is comparing two different things**.

### Part J: can the route be traced with the racers gone?

`track_proof.png` shows, per moment and per variant: the normal frame, the same
frame with everything but the channel taken to a fifth, the channel and machine
on black, and the racers painted out in the room's own median colour.

| | hook | chase | sparse | comeback |
|---|---|---|---|---|
| traceable channel, control | 99.2% | 100.0% | 100.0% | 100.0% |
| traceable channel, **B** | 98.5% | 99.9% | 99.9% | 99.7% |
| longest continuous run, all four | **100%** | **100%** | **100%** | **100%** |
| local ΔE p5, control | 22.4 | 23.1 | 54.6 | 51.6 |
| local ΔE p5, **B** | 20.8 | 19.9 | 37.4 | 36.7 |

A channel pixel counts as traceable when it is at least 12 ΔE from the median
room colour **in its own 64-pixel tile** — the room is not one value, and a
channel crossing a lit floor panel has a different job from one crossing a
shadowed wall.

**The measure saturates, and that is the result rather than a fault.** Every
candidate, including the control, returns 98–100% on every racing moment, and
the longest continuous traceable run is the full width of the frame in all four.
The raceway is not blending into the environment and never was. What B costs is
visible in the last row — its dark lip band brings the fifth-percentile pixel
closer to the room — and 37 ΔE is still sixteen times a just-noticeable
difference.

---

## 8. Phone review — 270×480

`phone_270.png` pastes the delivered frames at exactly 270×480 rather than at a
sheet-sized thumbnail, and every candidate also ships as a full film at that
size, because what a surface treatment has to survive is motion.

Against the brief's six questions:

1. **Can I see the full lane width?** No, in every candidate, and no material
   can change that — section 2.1. The lane is behind its own rail.
2. **Can I see where the track turns?** Yes in all four; the ribbon is
   continuous across the frame at every racing moment (§7).
3. **Can I separate deck from environment?** Yes in all four, by 57–70 L*.
4. **Can I separate deck from rail?** **Only in B.** The control's crown-to-face
   step is 1.2–2.4 L* through the race and inverts to −0.9 at 12.20 s; B holds
   7.1–9.5 L* at every moment. At 270 px this is the only difference between the
   candidates a viewer can actually point at.
5. **Do the racers still dominate?** More than before. The track comes down 5.1
   L* toward them and the weakest racer's separation from the track *rises*
   (§9).
6. **Does it look physical and premium?** B reads as a solid extruded kerb —
   catching light on its top edge, gradating down its face, shadowed where it
   meets the road. The control reads as a strip of white paper. A and C read as
   slightly greyer strips of white paper.

---

## 9. Racer contrast — Part K

Every racer measured individually, from the labelled mask, against the track it
is on and against the room.

| | control | A | **B** | C |
|---|---|---|---|---|
| weakest racer vs track, ΔE | 22.19 | 24.33 | **26.04** | 23.49 |
| mean racer vs track, ΔE | 66.77 | 65.92 | 65.12 | 66.48 |
| racers − track, ΔL* | **−27.68** | −24.86 | **−22.21** | −26.70 |

**Every variant improves the weakest racer's separation**, and B improves it
most, by 3.85 ΔE. The mean falls slightly for the same reason the weakest rises:
the track moves *toward* the middle of the racer set in lightness, which costs
the racers that were already far from it and helps the one that was closest —
and the guard the brief asks for is the weakest, not the mean.

The hierarchy is still not fully righted. B leaves the track 22.2 L* above the
mean racer. Closing that entirely would mean a track near L* 65, which the ladder
in §3 says costs 20 points of separation from the room and, more to the point,
stops being a premium light-grey raceway. **The track is a neutral surface and
the racers own all the chroma; that is the hierarchy the format needs, and the
last 22 points of lightness are not worth buying.**

---

## 10. Mechanism contrast — Part L

| separation from the track, ΔE | control | A | **B** | C |
|---|---|---|---|---|
| station bodies (orange) | 57.00 | 55.28 | **54.69** | 55.43 |
| moving blades | 60.12 | 58.33 | **57.68** | 59.17 |
| graphite structure | 43.93 | 43.18 | **43.48** | 46.94 |

Nothing is flattened. The largest loss is 2.4 ΔE on a separation of 57, which is
under 5%, and every class stays above 43 ΔE — nineteen times a just-noticeable
difference. The track is still the stage.

---

## 11. Switchbacks — Part H

8.40 s is the hardest frame in the film for this pass and for V31 before it: the
channel is **1.011% of the picture**, its smallest anywhere, and the field is
strung out.

| at 8.40 s | control | **B** |
|---|---|---|
| wall face L* | 79.9 | 77.1 |
| crown L* | 83.2 | 85.5 |
| crown − face | 3.2 | **8.3** |
| track vs room, ΔL* | 61.8 | 59.4 |

The viewer does not see the 180-degree fold — V31 established that no lens
standing behind the pack on a course that folds every 32 units can — and B does
not change that. What B changes is that the fragment of channel which *is* in
frame reads as a solid banked edge with a top and a bottom rather than as a
bright sliver. The local route shape is legible; the whole hairpin is not.

---

## 12. Final sprint — Part M

| | control | A | **B** | C |
|---|---|---|---|---|
| sprint track L* (t ≥ 13 s) | 85.89 | 82.59 | **79.74** | 84.03 |
| course track L* (2 ≤ t < 13 s) | 84.15 | 81.52 | **79.01** | 83.57 |
| sprint − course | **+1.74** | +1.07 | **+0.73** | +0.46 |

The control already runs the sprint 1.74 L* hotter than the course — that is the
room's own finish lighting, not the track — and B **narrows** it to 0.73. No
variant has a section-specific value and none could: one material, one texture,
applied to every run. Part N is satisfied by construction and Part M by
measurement.

The sprint's continuity, top-three readability, finish visibility and winner
readability are V31's and are untouched: the camera, the cut, the gantry and the
marks are all the delivered ones.

---

## 13. The winner: B

| | control | A | **B** | C |
|---|---|---|---|---|
| channel L* | 82.05 | 79.33 | **76.93** | 81.32 |
| channel L* spread (p95 − p5) | 28.02 | 26.56 | **39.05** | 22.10 |
| wall face L* | 86.08 | 83.28 | **80.95** | 84.98 |
| wall face spread | 15.27 | 14.67 | **21.89** | 12.06 |
| crown L* | 87.71 | 84.92 | **88.41** | 86.14 |
| **crown − face (the edge)** | **1.63** | 1.64 | **7.46** | 1.16 |
| cradle L* | 33.48 | 31.95 | **35.62** | 36.89 |
| lip L* | 68.53 | 67.18 | **56.67** | 72.55 |
| track vs room, ΔL* | 64.97 | 62.26 | **59.86** | 64.25 |
| weakest racer vs track, ΔE | 22.19 | 24.33 | **26.04** | 23.49 |
| racers − track, ΔL* | −27.68 | −24.86 | **−22.21** | −26.70 |
| rendered warmth, R−B | +0.69 | +4.26 | **+4.65** | +4.34 |
| clipped pixels | 0.00% | 0.00% | **0.00%** | 0.00% |

Against Part S's priority order:

1. **Continuous track readability** — level across all four at 100% of the frame
   width (§7); B is the only one that makes the continuous thing read as a
   surface.
2. **Racer readability** — B is best, by 3.85 ΔE on the weakest racer.
3. **Track physicality** — B is the only candidate with an edge: 7.46 L* against
   1.63, and 43% more internal modulation on the face.
4. **Switchback readability** — B, 8.3 L* of edge against 3.2 at the worst frame.
5. **Premium quality** — B reads as an extruded kerb; A and C read as the
   control slightly greyed.
6. **Restraint** — no emission, no rim, no glow, no stripe, zero clipped pixels,
   one texture 256×1, and a steep ramp only where the section has its one
   corner.
7. **Phone performance** — identical: same meshes, same triangles, same
   materials.

**B is not the brightest variant.** It is the darkest of the four by channel
mean, and it wins on the two things the brief actually asked for — a raceway
that reads as a physical surface, and racers that dominate it.

---

## 14. Performance — Part O

| | control | A | **B** | C |
|---|---|---|---|---|
| mesh instances | 326 | 326 | 326 | 326 |
| triangles (scene) | 93404 | 93404 | 93404 | 93404 |
| triangles (course) | 25420 | 25420 | 25420 | 25420 |
| course materials | 3 | 3 | 3 | 3 |

| ms per frame, 13 stills | 190 | 188 | **190** | 189 |

The variants draw the same scene. B adds one 256×1 `FORMAT_RGBF` texture — 3072
bytes — and nothing else. Per-frame cost spans 188 to 190 ms across the four,
which is 1% and inside run-to-run noise. The numbers are in
`docs/validation/race2/v311_track/cost.json` and
`test_performance_is_unchanged` asserts the first four rows are identical.

---

## 15. Remaining weaknesses

1. **The lane is still behind its own rail.** The cradle is 0.000% of eight of
   thirteen sampled frames and this pass does not change it by one pixel. A
   viewer never sees the road; they see the wall of the road. Fixing that is a
   *camera or course* question — either a lens more than six degrees above the
   channel plane, or a shallower descent, or a lower guard — and all three are
   locked, correctly, by this brief.
2. **The hierarchy is improved, not righted.** B leaves the track 22.2 L* above
   the mean racer. §9 argues that the remainder should not be bought.
3. **B's lip costs the darkest channel pixels some local separation** — fifth
   percentile 54.6 → 37.4 at the 10.60 s chase. Still sixteen JNDs, and it is
   the price of the shadow line that creates the edge.
4. **12.20 s is the one moment B's edge is weak** — 2.6 L* against its 7–9.5
   everywhere else. The channel there is small, steeply lit and mostly crown;
   there is very little face in frame for the gradient to run down.
5. **The whole pass is worth about eight L\* on one band.** That is what a
   material can do here, and it is worth being plain about the size of it: the
   readability headroom left in Race #2 is not in the channel's surface.

---

## 16. Should track development stop here?

**Yes.** Against the brief's own stop condition:

- **a visibly continuous raceway** — 100% of the frame width, every moment,
  measured with the racers masked out;
- **clear local route shape** — the ribbon reads as a banked surface with a top
  edge and a shadowed foot rather than as a line;
- **readable switchbacks** — improved at the hardest frame in the film, 3.2 →
  8.3 L* of edge, with the honest limit in §11;
- **good phone visibility** — the deck/rail separation is the one difference
  visible at 270×480, and B is the only candidate that has it;
- **racers remain dominant** — every racer separates better from the track than
  it did, and the weakest by 3.85 ΔE;
- **premium rather than glowing** — no emission anywhere, zero clipped pixels,
  and the winner is the *darkest* of the four.

Do not create V31.2. The evidence for stopping is §15.1 and §15.5: the surface
has one band on screen, that band now has form, and it is worth about eight L*.
Everything left in Race #2's track readability is behind the near rail, and
reaching it means moving the camera, the course or the guard — a different brief
from this one, and one that would have to re-open locks this pass was told to
hold.

---

## 17. What was produced

Films, all 1150 frames — 19.167 s at 60 fps, frame 0 to frame 1149, contiguous,
asserted by `test_the_delivered_clips_have_no_temporal_omissions`:

```
exports/race2_v311_track/
  race2_v311_v31.mp4                       the control film
  race2_v311_A.mp4  race2_v311_B.mp4  race2_v311_C.mp4
  race2_v311_production_preview_B.mp4      the winner, with PICK A COLOR,
                                           the winner ring and the payoff card
  race2_v311_control_vs_A.mp4              side by side, 540x960 each
  race2_v311_control_vs_B.mp4
  race2_v311_control_vs_C.mp4
  race2_v311_quad_control_A_B_C.mp4        4-up, whole film
  race2_v311_quad_opening.mp4              4-up, per section
  race2_v311_quad_first_mechanisms.mp4
  race2_v311_quad_visibility_problem.mp4
  race2_v311_quad_switchback_chase.mp4
  race2_v311_quad_final_sprint.mp4
  race2_v311_{v31,A,B,C}_phone_270x480.mp4 every candidate at phone size
```

Sheets and reports:

```
docs/validation/race2/v311_track/
  track_measure.json    every table in sections 2, 9, 10, 12 and 13
  traceability.json     section 7's Part J numbers
  cost.json             section 14
  sheet_180.png         variant x 13 moments
  phone_270.png         variant x 6 moments, pasted at 270x480
  track_proof.png       normal | track | environment-suppressed | racers-masked
  preview_placement.json  the measured title band and the ring's occlusion test
```

The production preview's own checks, printed when it builds: the title takes the
high band with 352 px of clearance against the racers' 101; the winner ring runs
16.00–16.70 s over m7 for 43 frames with **0 hidden**; the payoff card is in
m7's own pink, `rgb(240, 85, 155)`.

---

## 18. Reproducing it

```bash
export GODOT_BIN=~/Downloads/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe
python tools/race2_camera.py --course=switchyard --seed=8   # replay + geometry
python tools/race2_cine.py --seed=8 --only=A                # the V28.1 control
python tools/race2_v31_camera.py --seed=8                   # the RB camera track

python tools/race2_v311_track.py masks     # the segmentation, once
python tools/race2_v311_track.py stills    # control + A + B + C
python tools/race2_v311_track.py probe     # section 3, one field at a time
python tools/race2_v311_track.py measure   # every table above

python tools/race2_v311_review.py proof        # sections 7 and 11
python tools/race2_v311_review.py sheet
python tools/race2_v311_review.py phone        # 270x480, mandatory
python tools/race2_v311_review.py clips        # four 19.15 s films
python tools/race2_v311_review.py compare      # control | A, | B, | C
python tools/race2_v311_review.py quad         # control / A / B / C
python tools/race2_v311_review.py phonefilm
python tools/race2_v311_review.py cost
python tools/race2_v311_review.py preview --winner=B

python -m pytest tests/test_race2_v311_track.py
```

The replay is read, never re-simulated. `tools/race2_camera.py` rebuilds it from
seed 8 and it reproduces with the same `digest` and `event_digest` the delivered
film was cut from — the only field that differs between two runs is
`summary.race.wall_seconds`, which is how long the simulation took.
