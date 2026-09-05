# Neon Marble Machine — visual polish (V1.1)

The V1 prototype answered one question: does a paused frame obviously look
three-dimensional? It did, and the architecture behind it — a course that
exports where its bowl is, and a scene that is *told* rather than left to infer
— was accepted as the direction.

This revision does not extend it. Same three sections, same seven seconds, same
1080×1920. What it does is take the five weaknesses the V1.1 brief names and
close them, so that a random paused frame reads as a premium 3D marble-machine
video rather than as a technically impressive prototype.

Reference: `docs/references/neon_marble_machine_concept.png`, matched for
hierarchy — light track on dark structure, glass-and-metal bowl, suspended
bridge with air under it, controlled neon accents — not for decoration.

Before and after, at matched timestamps:
`docs/validation/neon_v11/before_after/`.

---

## How to run

```bash
# everything: replay, cameras, sequence, stills, video, countries, sheets
python tools/neon_proof.py --seed 7 --all

# or one step at a time
python tools/neon_proof.py --seed 7 --replay
python tools/neon_proof.py --seed 7 --cameras --angles 48,52,55
python tools/neon_proof.py --seed 7 --frames --sections --heroes
python tools/neon_proof.py --seed 7 --video --countries --before --phone

# the course on its own, with no renderer involved
python race_main.py --course neon --racers 16 --seed 7 --headless
python -m tools.course_audit --course neon
```

Godot is found the way the rest of the project finds it: `--godot`, then
`$GODOT_BIN`, then the PATH.

---

## What changed, in one table

| Brief's problem | What it was | What it is |
| --- | --- | --- |
| **1. Start too large and flat** | one apron 890px wide, six units of pale deck between the lens and the bowl | four launch channels 150px wide, divided by ribs, merging in pairs into two spouts. The platform is four loading bays over the same ribs |
| **2. Bowl not premium** | a metallic dish; the acrylic under the vessel where the lens cannot see it; the cradle inside its own rim | a flared acrylic wall standing *on* the rim with the field inside it, a machined rim with clamps, a cradle outside the flange, underlighting |
| **3. Background empty** | two ranks of columns, 4% brighter than black | a hall: three ranks of structure at three distances, a floor with plant on it, conduits, braces, light runs |
| **4. S-curve procedural** | a flat ribbon, constant side normals, a post every 2.6 units | a five-value cross-section on a deep girder with web stiffeners, and five supports of three designs placed at the ends and the apexes |
| **5. Palette too gray** | cool light silver on graphite, in a mostly black frame | warm light silver, structure lifted two steps, room lifted three, and 33–68% of the frame no longer near-black |
| Throat disappearance | half a second of racers gone under the bowl | a glazed window in the far half of the bowl's floor, which is the only surface between the lens and the throat |
| Country balls | flags wrapped over spheres, rejected | a badge above a plain marble, in two candidates, compared at three moments and at phone size |

Measured, rather than claimed:

| | V1 | V1.1 |
| --- | --- | --- |
| Frame that is near-black (max channel ≤ 12), `inside_bowl` | 32.7% | **1.8%** |
| ...`s_curve_bridge` | 68.0% | **8.2%** |
| ...`start_platform` | 63.4% | **15.0%** |
| Mean pixel value, `inside_bowl` | 97 | **122** |
| Course audit, neon | 0 errors, 21 warnings | **0 errors, 15 warnings** |
| Seeds of 30 finishing 16/16 with no recoveries | 29 | **30** |

---

## Part 1 — the start

The V1 report called the chute apron the largest pale surface in the picture
and the brief agrees. It was one channel 890 pixels wide, and the renderer draws
whatever channel the walls make, so it drew six units of unbroken deck between
the lens and the bowl — hiding the cradle, the legs and the space underneath.

The replacement is a **course** change, and it had to be. The deck builder
derives its ribbons from the clear spans between walls; the only way to get four
channels with gaps between them is for the course to have four channels with
ribs between them.

```
 105                                                          975
  |  lane 150  | rib 90 |  lane  | rib |  lane  | rib |  lane  |
  |            four launch channels, y 740 -> 1030             |
   \__________________________/   \__________________________/
          left feed                       right feed              y 1030 -> 1190
              \________/                       \________/
                left spout                     right spout        y 1190 -> 1350
```

* **The lane is 150px** — two and a half racer diameters, so racers pass each
  other rather than queueing.
* **The rib is 90px**, and that number is set by the drawn gap rather than by
  the simulation. Each deck reaches past its own wall so the rails have
  something to stand on; at the standard 32px margin the four decks close to
  within 26 pixels of each other, which reads as a scratch on one deck rather
  than as four decks. The launch section uses a 22px margin instead, so the gap
  is 46 — and 46 pixels of nothing is where the frame beneath shows through.
* **The ribs are carried up through the platform**, so the deck is four loading
  bays and the field stands in the channels it is about to be released into.
  Without them the sixteen marbles settle onto the gate as one row across the
  full width, and any rib *drawn* on the deck would have marbles sitting on both
  sides of it and through it.
* **Four marbles to a bay**, because the grid is derived from the lanes rather
  than from a pitch. That is also what makes "synchronised lane release" mean
  something a viewer can see: the gate is one blade per channel and four
  channels empty at the same instant.

Drawn on top of that: a dark block the bays are let into, so the platform is a
machined component with channels cut in it rather than four planks side by side;
fins between the bays with polished caps and one cyan line; a deep fascia beam
across the front with a lit inset; legs, three levels of cross-tie and a
diagonal per side; and the START sign on a gantry with posts, shoes, a header
beam and a bezel round the lit panel. V1 hung a bare white slab off two posts,
and a bare emissive rectangle is a sticker.

### The two failures the merge went through

Both are recorded because each one was caused by fixing the other, and the
combination is what the file ships.

**A thick leaning wall has an outside.** Its inner face arrives at the spout
while its outer face is still back at the boundary, and the wedge between them
is a sealed void the audit correctly reports as a trap. Offsetting a *polyline*
outwards fails the same way at every joint: two offset segments that meet at a
point on the inner face diverge everywhere else, so the convex side of each turn
opens a V. At the thickness needed to reach the boundary those Vs came out
65 pixels wide — wider than `MIN_SPAN` — so the deck builder swept a ribbon
through each of them and the chute grew four phantom channels.

**A staircase of vertical blocks has ledges.** It has no outside and no holes,
and every step's top face is a seven-pixel horizontal shelf. A racer pressed
onto one by the racer behind it stays there. Eight of thirty seeds lost a marble
to a shelf on this merge and the recovery system teleported it out — which is
the one thing a viewer would certainly notice inside a seven-second clip.

So the wall is **both**: a thin facing wall along the exact line a racer
touches, offset perpendicular so its face *is* that line, and a staircase
filling everything behind it. The fill's face is set a step and a half short of
the wall's, which puts every one of its shelves inside the wall's own body —
interior to the union, and unreachable. What a racer meets is smooth; what the
audit measures is solid to the boundary.

The rib ends got the same treatment for the same reason: a rib that just stops
leaves two convex corners, and the contact normal at a corner points a few
degrees above horizontal, which is enough to hold a marble that something else
is pushing onto it. Each outer rib ends in a dome wider than itself, so its
corners are inside a circle and there is nowhere to rest.

**Result: 30 of 30 seeds finish sixteen from sixteen with no recoveries and no
retirements**, against 29 of 30 for V1.

---

## Part 2 — the bowl

V1 built the right shape and the report was honest that it read as a satellite
dish. Three things were missing.

### The glass is above the rim, not under the vessel

V1's acrylic shell sat *beneath* the bowl, where at a 52° lens there is almost
none of it in view — the report listed that as a real limitation. The
reference's bowl is a flared transparent wall standing **on** the rim with the
racers inside it, and that is what reads: silhouetted against the dark room,
catching a Fresnel edge all the way round.

It costs nothing in readability because of one decision: **the wall is an arc
with 88 degrees cut out of the near side.** A closed ring of glass would put a
film between the lens and every marble in the bowl. An opening on the side the
lens is on puts glass everywhere it can be seen *against* the room and nowhere
it would be seen *through*. The opening is also where the feed spouts arrive, so
it is a thing the machine needs rather than a thing the camera needs — the two
are the same place because the lens and the field come in from the same side.
`test_the_acrylic_wall_stands_on_the_flange_and_leaves_the_field_a_way_in`
asserts the gap is wider than the arc the spouts occupy.

The wall carries a capped top rail with a thin lit line — the one thing a
transparent object cannot do for itself is draw its own silhouette — jambs at
both ends of the arc, and five mullions on the far half only, where they read
against the room and never between the lens and a marble.

### The rim is a machined assembly

A flange one value below the racing surface, a dark structural band beneath it
one value below that, twelve clamps around it (the fixings the acrylic is bolted
down by, and the only thing on the rim with a rhythm), one cyan inset, and two
machined seams across the dish. A bowl with no surface incident renders as one
enormous smooth gradient, and a gradient is the one thing that does not read as
a manufactured object.

### The cradle is outside the vessel's silhouette

V1's hoop was at bowl radius 0.86 — underneath the dish, inside its own
silhouette, invisible from any lens high enough to see into the bowl. Moving it
to 1.30 was not enough either: at 1.30 it is still under the acrylic wall's
flare at the bowl's edges and only shows as a smudge through it. **1.42** puts
it outside everything, and from every frame in the shot there is now a dark
machined ring standing below and outside the vessel with six arms into it, six
legs to the floor, two collars tying them together, and eight lit strips —
cyan on the drain side, violet opposite.

`test_the_cradle_stands_outside_the_flange_it_is_holding` asserts the radius,
because the failure mode is silent: the geometry is still correct, it is just
not visible.

### Layers, as the brief lists them

```
acrylic wall        rho 1.20 -> 1.42, rising 0.95 above the rim, 88 deg cut out
racing surface      rho 0.23 -> 1.00, opaque light silver with a clearcoat
flange and rim      rho 1.00 -> 1.20, one value down, banded and clamped
structural shell    the same surface 0.26 below, dark rather than mid-grey
cradle              hoop at 1.42, six arms, six legs, two collars
underlighting       eight strips, plus two omnis under the vessel
```

The racing surface stays **opaque**, and that is a decision rather than an
omission. A translucent one loses the contact shadow under every marble and the
terminator across the curve, and those two are what prove the bowl is a bowl.

### The throat window

The brief asks for the half second the racers spend under the bowl to be made
intentional or removed. It is now a window.

Between the drain and where the bridge emerges from under the far rim, the only
surface between the racers and the camera is the bowl's own floor — and it is
the **far half** of it, which nothing ever stands on. The mapping sends anything
past the drain plane down the throat, *below* the floor, so a 50° sector of the
far half from bowl radius 0.30 to 0.88 is free to glaze. It is framed on all
three sides, because an unframed hole in a machine is a missing piece, and lit
from below by a pale cyan omni so the window shows a lit channel rather than a
dark wedge.

What it buys: the field is visibly still travelling. It is the most striking
single frame in the clip — see `docs/validation/neon_v11/sections/bowl_exit.png`,
where half the field is descending inside the machine while the rest is still
ringed around the drain.

Two assertions guard it. The geometric one: the window is a sector centred on
the point of the disc furthest from the lens, so every point of it is past the
drain plane. The behavioural one: `deck_height` still sends everything past that
plane down the throat, checked by reading the branch out of the GDScript, and
over the reference race more than two hundred racer-frames actually cross under
the window — a window onto nothing would pass a weaker test.

---

## Part 3 — the environment

V1 built a dark void with two ranks of columns in it, and the brief is right
that the result was mostly empty black. The columns were there; they were four
percent brighter than the background and eleven units to the side of a lens
whose frustum is six units wide at the subject, so almost none of them ever
crossed the frame.

What fills a portrait frame at this focal length is not what stands *beside* the
machine — it is what stands *beyond* it. The frustum is six units wide at the
aim and grows by one unit for every five past it, so the top half of every frame
looks up the hall the machine is standing in.

So it is a hall. Three ranks at three distances, chosen against the lens rather
than by eye:

| Rank | Out | First crosses the frame | Reads as |
| --- | --- | --- | --- |
| Near towers | 8.7 | ~10 units past the aim | the fastest thing in the parallax |
| Mid towers | 12.9 | ~30 units past | banded, with braces reaching in |
| Wall panels | 17.4 | further again | a grid, on a backing wall |

Plus: a floor of the hall at −15 with plate joints across it, plant standing on
it in three sizes on a fixed cycle, a dim light run down each side, conduits
climbing the near towers (round against everything else being square, which is
the whole reason they are there), and braces reaching in from each side with a
diagonal stay into the tower under them — never a beam right across, because a
horizontal bar across a portrait frame reads as letterboxing.

**The floor was raised from −19 to −15, and that is a reversal of a V1
decision.** V1 reasoned that a dark void keeps the machine the subject and that
more air under the bridge is more obviously air. What it produced was a frame
that is mostly nothing, and posts ten units long: at a 52° lens a post projects
sixteen units *down the frame*, past the bridge and the throat and onto the back
of the bowl ten units nearer the lens, so every support on the bridge was drawn
behind the bowl's acrylic. At −15 the same posts project nine and land on the
floor directly under the deck they hold up. Six units of air under a deck three
and a half wide is still unmistakably air.

**Foreground, midground, background.** The brief requires all three in a paused
frame, and the foreground is the machine's own near structure — its list allows
exactly that ("rail / support / structural element / nearby machine edge"). At
this focal length nothing else can be there: the bottom of the frame at the aim
plane is 6.7 units below and 8.6 units nearer than the aim, which is where the
platform's legs, the chute's frame and the bowl's cradle stand. That is why they
were thickened rather than left as V1 had them.

---

## Part 4 — the S-curve

### The cross-section

V1 drew a deck as a flat ribbon with a rail at each edge. A manufactured channel
has a profile:

```
 rail            rail        polished, near-mirror
  | bevel  bevel |           one value down, catching the key
  |   \_______/  |           the running surface
  |    panel     |           one value down again, inlaid
 ========================    the girder, underneath and dark
```

Five values across a deck instead of two, and none is decoration. The bevel
gives the edge a highlight that is not the rail's. The panel stops a wide pale
surface reading as paper — and its **value was changed**: V1 used the deep tone,
which on a launch channel a unit and three quarters across read as a dark stripe
with track either side of it, turning a light silver deck into a dark one with
pale edges. One step below the running surface is enough to break a flat
surface; three steps is a different material.

The girder is what the supports meet. A post that ends at a flat underside ends
in mid-air; one that meets a beam is a joint. On the bridge it is deep (0.82)
with web stiffeners along it, and it is the single strongest cue that the deck
is in the air: a pale surface with a dark fabricated beam under it, lit on one
face and shadowed on the other, is an object standing in space.

### The lighting fix that made it stop looking generated

`_solid_ribbon` gave every side face a constant normal — `Vector3.RIGHT` on the
right, `LEFT` on the left. A bridge that turns through ninety degrees therefore
had its whole outer wall claiming to face the same way, so the key light landed
on it in flat bands that switched value at the sample joints. That, more than
the geometry, is what read as *generated*. The normal is now taken from the
edge's own direction in the horizontal plane, and the wall has a continuous
gradient around each bend.

### The supports

V1 dropped a post every 2.6 units and the brief is right that it looked like a
metronome. Positions are now chosen:

* the two ends, where the deck hands over to the next stretch
* every apex of the swing, where the centre line turns back and the deck is
  furthest out over the room
* the middle of any span still longer than 3.8 units

On this bridge that comes out as five: a bracket, a Y-frame, a filled pillar, a
Y-frame and a bracket. Three silhouettes, not one pole repeated.

| Type | Shape | Where |
| --- | --- | --- |
| A pillar | a narrow splayed pair with a tie | under a straight run |
| B Y-frame | a mast to a yoke, two legs splayed wide | at an apex |
| C bracket | a leaning post with a raked strut behind it | at each end |

The apex detector needed one fix worth recording: a turn is flat at its extreme,
so "further out than both neighbours a window away" is true for a *run* of
consecutive samples — four either side of each apex here. The first version
built four Y-frames within a quarter of a unit of each other, which draws as one
support and costs three.

**Every support splays sideways**, and that is why they read at all. A vertical
post under a deck at a 52° lens is drawn nine units further down the frame,
which on an S-curve is exactly where the next bend of the same deck is. A leg
whose foot is a metre and a half outside the deck's own edge is beside it
instead, against the floor.

The chute is the exception: four channels with their own posts would be sixteen
legs in rows under a stretch three units long, and a thicket reads as noise. It
gets one frame — cross beams under all four, hangers, and a stringer down each
side — which is also what makes the gaps between the channels worth having,
because structure below them is only visible if it spans the gaps.

---

## Part 5 — materials and palette

`godot/scripts/neon_materials.gd`. The three rules are unchanged: the track is
light and the structure is dark, nothing is emissive unless it is a light, and
the picture has to survive with bloom off.

| Role | V1 | V1.1 | Why |
| --- | --- | --- | --- |
| Track surface | `#858A8F` cool | **`#9A9790`** warm, lighter | against cyan on graphite, a blue-grey track read as structure lit harder. Warm — red above green above blue — separates track from frame without adding a colour |
| Deck panel | the deep tone | **`#827F7A`**, one step | see above; three steps is a different material |
| Structure, lit | `#26282F` | **`#343739`** | V1's cradle, legs and braces were within a few hundredths of each other and the frame read as one silhouette |
| Room | `#0C0D10` | **`#151720`** near, `#15181D` far, `#0E1014` wall | three distances a viewer can tell apart |
| Floor of the hall | `#040507` | **`#141618`** | plant standing on an invisible floor reads as boxes floating in space |
| Rails | `#8F9AA6` | **`#A7ABB3`** | |
| Acrylic wall | — | `#9EC7DE` at **15.5%**, rim 1.0 | thin in body, strong at the edges: that is what acrylic looks like and what keeps it free |
| Throat glass | — | `#6690A8` at 21.5% | being looked *through* on purpose |
| Cyan / violet | unchanged | unchanged | one cool accent and one warm-violet, and no third |
| Racers | unchanged | unchanged | no emission at all; a clearcoat highlight and a rim light |

Measured composition, as a share of pixels (neutral = saturation under 0.30 or
very dark; accent = hues from cyan through violet; racer = everything else):

| Still | V1 neutral / accent / racer | V1.1 |
| --- | --- | --- |
| `inside_bowl` | 83.5 / 15.6 / 0.9 | **78.3 / 20.9 / 0.8** |
| `start_platform` | 87.9 / 11.4 / 0.7 | **80.9 / 18.4 / 0.7** |
| `s_curve_bridge` | 87.6 / 11.5 / 0.9 | **90.4 / 8.5 / 1.1** |

The brief's suggested 70 / 20 / 10 is explicitly approximate, and it is worth
saying where the measurement lands against it rather than claiming a match.

Neutral and accent are close on two of three stills. **Racer colour cannot reach
ten percent of a portrait frame at this framing** — sixteen marbles 0.3 units
across, seen from thirty units, are about one percent of the pixels whatever the
palette does.

And the marbles are **not** the most saturated thing in the frame by area, which
is worth saying plainly because it would be easy to claim otherwise. Above 0.60
saturation in `bowl_hero`, cyan and violet take 2.26% of the pixels and racer
hues take 0.30% — the accents outweigh the marbles about seven to one. What
makes the marbles read as dominant is not area but variety and locality:
sixteen distinct hues, all of them on the part of the frame the eye is already
tracking, against one accent family used only along edges. That is a real
argument rather than a measured one, and it is the honest way round.

The bridge went the other way — its accent share fell, because the hall behind
it is new and neutral. That is the honest reading: the bridge stretch is
*larger* now and most of what was added to it is room.

### Lighting and exposure

Key, fill and kicker are unchanged from V1; what changed is what they land on.
Measured on the shipped sequence:

| Frame | Clipped (max channel ≥ 254) | Near-black (≤ 2) |
| --- | --- | --- |
| `start_platform` | 0.13% | 0.27% |
| `start_hero` | 0.15% | 0.31% |
| `bowl_hero` | 0.25% | 0.06% |
| `bowl_exit` | 0.28% | 0.10% |
| `s_curve_bridge` | 0.04% | 1.30% |
| `bridge_hero` | 0.06% | 1.57% |

No crushed supports, no blown track. What clips is the START panel, the drain
collar and the key's own highlight on the bowl — the three things that are meant
to.

### Bloom

`--neon-no-glow` renders the same frame with glow disabled, so the brief's "the
image should still look good with bloom disabled" is answered by looking rather
than by asserting, out of one build of one scene from one replay:

| Frame | Mean absolute difference | Pixels differing by more than 8 |
| --- | --- | --- |
| `start_hero` | 0.69 / 255 | 1.10% |
| `bowl_hero` | 1.06 / 255 | 2.05% |

The two frames are the same picture. What is lost is a small halo around the
drain collar and the START panel. Every value, edge and shadow comes from
albedo, roughness and the key light.

---

## Part 6 — the camera

`tools/neon_proof.py --cameras` renders the same four moments of the same replay
through the same scene at each elevation; only the lens differs. Stills are
under `docs/validation/neon_v11/camera/e48|e52|e55/`.

V1 swept 42 to 56 to find the range and settled both ends: 42 hides the bridge's
supports behind the deck they hold up, and 56 flattens the bowl towards a plan
of itself. This revision compares *inside* that range rather than re-deciding
it.

| | Bowl depth | Support structure | Bridge elevation | Racer readability |
| --- | --- | --- | --- | --- |
| **48°** | far wall compresses; the drain narrows to a slit | best — most side-on | best | marbles crowd at the drain |
| **52°** | interior and far wall both readable, drain round | good — both apexes in view | good | good |
| **55°** | roundest bowl, drain fully open | flattest | weakest | best separation |

**Selected: 52°**, FOV 40, portrait 1080×1920.

48 and 55 each win two of the four criteria and lose the other two, so the tie
went to the measurable one the brief singles out elsewhere: a height difference
projects onto the screen's vertical axis in proportion to `cos(elevation)`, so
52° separates the platform, the bowl and the bridge 8% more than 55° does — and
the height hierarchy is the thing V1 proved and this revision must not spend.
52° also keeps the drain round, which matters more now than it did in V1,
because the drain is where the throat window points.

### The move

One flowing shot, no cuts. Every term is a smoothstep of the aim's course
height, so the framing is a pure function of the playhead: seeking anywhere
gives the same frame and two renders agree exactly.

| Phase | Distance | Elevation | Aim |
| --- | --- | --- | --- |
| Platform | ×1.15 | 52° | rides the deck |
| Into the bowl | ×0.97 | 49° | drops 0.35 to look in |
| Along the bridge | ×1.00 | **48°** | lead extended by **950px** |

Two numbers changed from V1 and both are about the supports.

The bridge phase now **dips** four degrees instead of climbing one. The bridge
is the stretch whose whole point is that there is air under it, and a lens that
climbs while the field crosses it looks further down onto the deck and hides the
girder, the posts and the space they stand in behind the deck they hold up.

The bridge lead went from 520 to **950** course pixels. At the shorter lead the
bowl sits across the bottom third while the field is on the bridge, and every
support projects down the frame *onto the back of the bowl*. Carrying the aim
three and a half units further along puts the bowl out of the bottom of the
frame and the floor of the hall behind the posts.

Under all of it, the same slow eight-degree orbit applied to the camera position
and not to the aim, so the machine stays centred while the three ranks of the
hall sweep across the frame at three visibly different rates.

---

## Part 7 — the country badge experiment

`--neon-countries=flag` and `=code` swap the first five racers and change
nothing else, so the three stills in a row differ in exactly one thing. Sheets
are at `docs/validation/neon_v11/countries/{start,bowl,bridge}.png`, and again
at phone size under `phone/`.

Both candidates are the same object with a different graphic on it: a circular
plate in a dark bezel, billboarded above the marble, with the three-letter code
under it. The marble underneath keeps one country-inspired hue — identity is
meant to come from the badge, and a body carrying a whole flag would be the
thing the brief rules out wearing a different name. India saffron, Japan white,
Brazil green, USA navy, Germany gold: one hue each rather than a scheme, because
these are the *marbles* and they have to stay separable from each other in a
pile-up of sixteen.

No wrapped flags. `test_the_five_countries_are_the_ones_the_brief_names` asserts
that `neon_flags.gd` contains no `albedo_texture` at all.

**Verdict, offered rather than decided.**

* **At full resolution the flag plate wins for high-contrast flags and loses for
  detailed ones.** Japan reads instantly — one motif, maximum contrast. Brazil
  reads. Germany reads as three bands. India comes through as an orange-white-
  green blob with the chakra gone, and the USA as a pale striped disc that could
  be several countries. This is the same split V1 found on the wrapped balls,
  which suggests it is a property of the flags rather than of the treatment.
* **The three-letter code is uniformly legible at full resolution** and is the
  fairer test of the two — it fails nobody.
* **At phone size neither is legible.** The plate is 0.40 world units across,
  which at this lens is about 35 pixels at 1080×1920 and about 10 at the
  302×538 preview, and 10 pixels holds neither a flag nor three letters. This is the finding that matters, because a Short is
  watched at the second size.
* **What survives at phone size is the marble's own colour.** A saffron ball, a
  white ball, a green ball, a navy ball and a gold ball are all still separable
  at 11 pixels.

**Recommendation:** if country identity is wanted, carry it primarily on the
*body colour*, use the flag plate as the full-resolution reward for viewers
watching larger, and keep the code as the fallback for flags that do not survive
simplification. Do not size the badge up to make the flag work at phone size —
the brief's own constraint is that it must stay small enough not to clutter a
pile-up, and the bowl sheet shows how quickly five badges start to overlap.

Not carried into the racer system, as instructed.

---

## Part 8 — the deck builder, and its tests

The V1 report ended with a limitation this brief promotes to a requirement:

> The deck builder has no test, and it earned one.

`rendering/deck_geometry.py` is that builder in Python — a transcription of
`_piece_span`, `_clear_spans`, `_deck_ribbons`, `_smooth` and the shaping
helpers, function for function, in the same order — and `tests/test_deck_geometry.py`
is what makes keeping it worth anything. **17 tests.**

Nothing in the production pipeline imports the port. The tests do.

### Keeping the two from drifting

* Every constant the two share is parsed out of `neon_scene.gd` and asserted:
  `DECK_MARGIN`, `DECK_STEP`, `MIN_SPAN`, `EDGE_SMOOTHING`, `WALL_SIN_MIN`. A
  value edited on one side and not the other fails the suite rather than the
  render. (`WALL_SIN_MIN` was a bare `0.25` inside a function and is now a named
  constant, so it can be checked.)
* The three lines carrying the historical fixes are asserted to still be there.
  Asserting on source text is a blunt instrument and the right one here: these
  are not behaviours the suite can reach, and each is a line somebody could
  delete while tidying.

### What the brief asked for, and where it is

| Required case | Test |
| --- | --- |
| rotated wall span calculation | `test_a_leaning_wall_is_measured_at_the_height_it_is_asked_about` — a box at 45° measured at three heights: the centre must track the lean and the width must stay the box's thickness across it, not its diagonal |
| changing channel count | `test_changing_the_channel_count_leaves_nothing_unswept` — the closing runs and the opening runs meet on one plane, to floating-point equality |
| continuity between deck ribbons | `test_every_ribbon_is_continuous_along_its_own_length` — every section, every run, no gap over one sampling step and no edge jump over 90px |
| no unsupported racer positions | `test_no_racer_is_ever_over_open_air` — every racer, every frame, over drawn deck, on a recorded race |
| no one-sample gaps | covered by the continuity test above; `test_every_section_is_swept_to_its_own_planes` covers the seams between sections |
| no deck under open void | `test_a_gap_open_to_one_side_is_not_a_channel`, `test_a_gap_narrower_than_a_racer_is_not_a_channel`, `test_the_gaps_between_the_launch_channels_are_never_paved` |

Plus, because this revision's geometry is new: the launch section is four
channels and then two, the platform is four bays over the same four channels,
and smoothing leaves the S-curve's centre line within sixteen pixels of the
function the walls were placed from — a real bound rather than a comfortable
one, since a moving average over seven samples pulls the crest of a curve
inwards and the measured worst case is fourteen.

### A third defect, found by the port

The port earned its keep immediately. Sweeping a section stops two pixels short
of its bottom — at the plane itself this section's walls have ended and the next
section's have begun, which reads as a change of channel count and splits every
run. That left two course pixels of nothing at every seam between two stretches
of track. Two pixels is a fiftieth of a world unit and invisible; a racer
standing over it is standing over nothing, which is the one thing the whole
mapping exists to prevent. Every run that reaches a plane is now carried to it,
on both sides, in both implementations.

---

## Part 9 — determinism, and the production path

Frames 145, 301 and 499 were rendered by two separate Godot processes from the
same replay, and the PNGs are byte for byte identical:

```
still_000145   ea6cb7df1dfd21a8   ea6cb7df1dfd21a8
still_000301   c656eb28a5512fd0   c656eb28a5512fd0
still_000499   75621fced126a127   75621fced126a127
```

Nothing in `neon_scene.gd` accumulates across draws. The camera's framing is
computed from the frame in front of it, the shutter's position from the tick the
replay records the gate open, the racers from two frames and a blend, the plate
textures from an index with no randomness, and the hall's plant from a fixed
three-size cycle indexed by position.

**The production race path is unchanged, and this is a fact rather than an
argument.** Only six files differ from the V1 commit, and none of them is on it:

```
godot/scripts/neon_flags.gd      godot/scripts/neon_materials.gd
godot/scripts/neon_scene.gd      race/courses/neon.py
tests/test_neon_proof.py         tools/neon_proof.py
```

`race_scene.gd`, `race_materials.gd`, `replay_viewer.gd`, the simulation, the
exporter, the render plan and the battle path are untouched. Rendering three
moments of `output/race_v04/machine_20588_r16.json` through the production scene
gives the same hashes the **V1 report recorded**:

```
still_000210   5cb81a0a60504729
still_000840   54f16ced5ec59ae8
still_001440   9f241a80fd9d3ead
```

---

## Part 10 — the course audit

```
=== COURSE AUDIT: prototype ===   errors 0   warnings 3
=== COURSE AUDIT: split ===       errors 0   warnings 17
=== COURSE AUDIT: machine ===     errors 0   warnings 11
=== COURSE AUDIT: neon ===        errors 0   warnings 15
```

Neon is down from 21 warnings to 15, and it did not start there. The launch
channels introduced four errors of their own and each was closed rather than
explained:

| Was | Fix |
| --- | --- |
| a 34px pinch outboard of each spout wall, the wedge of void a leaning thick wall sweeps behind itself | the outer wall has no outside: a facing wall plus a fill to the boundary |
| the `start` checkpoint respawning onto the centre rib | respawn moved into the middle of a launch channel |
| four phantom channels swept through the Vs at the merge's joints | perpendicular offset for the facing wall, fill behind it |
| shelves on the fill catching racers | the fill's face set a step and a half behind the wall's, so every shelf is interior |

The remaining fifteen are **arch risks** — gaps a racer fits through that two
could bridge across — the same category the machine course carries eleven of.

---

## Part 11 — performance

RTX 3050 Laptop, Vulkan Forward+, 1080×1920, MSAA 2×.

| | V1 | V1.1 |
| --- | --- | --- |
| Render rate, full sequence (four runs) | 520–570 fps | **1260–1440 fps (0.7–0.8 ms/frame)** |
| Whole sequence (629 frames) | ~1.1s of GPU time | **~0.45s** |
| Encode | ~12s, 6.1 MiB | ~8s, **8.7 MiB** |

The rate went *up* despite roughly doubling the object count, because the scene
now spends much less of the frame on large transparent surfaces than V1's
full-ring acrylic shell did — the wall is an arc with 88 degrees removed and it
does not cast shadow. The hall's three ranks are MultiMeshes, one draw call
each.

The budget the brief allowed was spent on geometry, composition and lighting, as
instructed. No GI, no volumetrics, no particles, no reflection probes. The
prototype is still nowhere near a budget.

---

## Deliverables

| | Path |
| --- | --- |
| **Video** (7.00s, 1080×1920, 60fps, h264, no audio) | `output/neon_v11/neon_machine_polish.mp4` |
| Hero 1 — start platform, feeder tracks, bowl below | `docs/validation/neon_v11/start_hero.png` |
| Hero 2 — the field mixing, with glass and cradle | `docs/validation/neon_v11/bowl_hero.png` |
| Hero 3 — the S-curve with supports and depth | `docs/validation/neon_v11/bridge_hero.png` |
| Section progression, five moments | `docs/validation/neon_v11/sections/` |
| Camera comparison, 48 / 52 / 55 | `docs/validation/neon_v11/camera/` |
| Country badges, three treatments × three moments | `docs/validation/neon_v11/countries/` |
| Before and after, matched timestamps | `docs/validation/neon_v11/before_after/` |
| Phone-size review | `docs/validation/neon_v11/phone/` |
| Frame sequence and replay | `output/neon_v11/` |

Committed stills are written at half size, which is what `tools/race_moments.py`
does for the same reason: they are judged by eye, while anything measured is
measured on the full-resolution sequence under `output/`, which is git-ignored.
`--still-scale 1` writes them at 1080×1920 instead.

---

## Files

New:

```
rendering/deck_geometry.py            the deck builder in Python, for testing
tests/test_deck_geometry.py           17 regression tests over it
docs/neon_machine_visual_polish_v11.md  this file
```

Changed:

```
race/courses/neon.py            four launch channels, the merge, the rib domes
godot/scripts/neon_scene.gd     the start, the bowl, the hall, the supports
godot/scripts/neon_materials.gd the palette, the glass, the room depths
godot/scripts/neon_flags.gd     badges instead of wrapped flags
tools/neon_proof.py             heroes, badge sheets, before/after, phone
tests/test_neon_proof.py        the launch channels, the window, the badges
```

Untouched, and checked: `race_scene.gd`, `race_materials.gd`,
`replay_viewer.gd`, the simulation, the exporter, the render plan, the battle
path.

---

## What this does not do

Deliberately absent, per the brief's stop condition: the collector machine, the
split choice, the final compression, the finish arena, procedural generation,
race audio, curation, and the country badges as a system.

Real limitations, which is a different list:

* **The merged feed is still the largest pale surface in the frame.** Four
  narrow channels solved the first three hundred pixels; below the merge the two
  feeds are 350 pixels wide before they narrow to the spouts, and at the bowl
  moment that band takes the bottom fifth of the picture. It is about a ninth of
  V1's apron by area and it is broken by the wedge and four rails, but it is
  still the thing the eye lands on after the bowl. The hero course should route
  the field into the bowl on two *tracks* rather than on two feeds.
* **The bowl's cradle reads as a dark mass rather than as machinery.** It is
  outside the flange now and unmistakably present, but it is seen through the
  acrylic wall at the bowl's edges, which tints it and flattens its own
  modelling. A lower lens or a lit face on the hoop would fix it; both were out
  of scope here.
* **The hall is made of boxes.** Three ranks, plant and conduits is enough to
  sell scale, and at low contrast the boxiness does not read as boxes — but it
  is boxes, and a wider establishing shot would show that.
* **Racer colour cannot reach the brief's suggested ten percent** at this
  framing, and no palette change would get it there. See Part 5.
* **The badge fails at phone size.** Documented rather than hidden; the
  recommendation is in Part 7.
* **No trails, no impact effects, no HUD.** Still switched off on purpose so the
  architecture is what gets judged. The finished thing will need them and they
  will change the exposure balance measured in Part 5.
* **One seed, one course.** This is an art-direction proof, not a balance pass.
  What is measured about the race is that it does not break: thirty seeds,
  sixteen finishers each, no recoveries, no retirements, and no racer ever past
  bowl radius 1.11 against a drawn flange at 1.20.
* **The deck builder still assumes a course is a channel between two walls.** It
  copes with four channels merging into two because the count of gaps is
  tracked, but a genuine fork with two long parallel routes would need the
  matching to be smarter than "same count, same order". The Python port makes
  that a thing that can be developed against rather than discovered in a render.

---

## Tests

`tests/test_deck_geometry.py`, 17 tests. `tests/test_neon_proof.py`, 41 (25
before this revision). The whole suite is **1122 passing**, up from 1089.

Nothing was removed or relaxed. The three V1 tests that changed did so because
the values they pin moved: the camera sweep is now 48/52/55, the drawn flange is
1.20 rather than 1.16, and `--neon-countries` takes a treatment name rather
than a flag.
