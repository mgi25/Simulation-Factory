# V29: SWITCHYARD, camera A, and the contained hall

Branch `v29-switchyard-contained-integration`, from
`origin/v281-racing-cinematography` at `c218eee`, with V27.2's hall brought
across by path from `53821d3`.
**Nothing is merged. This branch collects evidence and fixes no environment.**

---

## 1. What this is, in one paragraph

Three finished things were put in one render for the first time: Race #2's
SWITCHYARD on hero seed 8, V28.1's camera A, and V27.2's `contained_hall_v272`.
The race is byte-identical to the one V28 and V28.1 filmed, the camera track is
the one `tools/race2_cine.py --only=A` solves, and the hall's profile chain is
V27.2's to the leaf. **The combined candidate renders, and it does not work.**
The delivered contained film is **64.9% pure black by area**, rising from 36%
in the hook to **90.8% through the whole 6.47 s final sprint**, and the racers
in that sprint fall from 128.3 luma in the outdoor control to **21.0**. The
cause is geometric and is stated in section 5. The hall authors geometry for
ten surfaces and **six of them never reach the film at all**, including both of
its warm practicals.

---

## 2. What was integrated, and what was deliberately left behind

Taken from `53821d3` by path - `git checkout 53821d3 -- <files>`, not a merge:

| | |
|---|---|
| `environment/environment_stage.gd` | new, V27's five stage builders |
| `environment/environment_world.gd` | V27's hunk: five keys interleaved into `BUILD_ORDER` |
| `lab_palette.gd` | V27's hunk: the eleven `hall_*` material keys |
| `profiles/contained_base.json` | V26 with the outdoor world and backdrop erased |
| `profiles/contained_hall.json` | the room |
| `profiles/contained_hall_v271.json` | the finish-bay pad correction |
| `profiles/contained_hall_v272.json` | the merge correction: one specular leaf |

The base is **identical to V27's parent** for both edited `.gd` files, so taking
V27.2's version of them applies V27's hunks exactly and loses nothing:

    environment_world.gd   base vs 31f8c05~1 : IDENTICAL   base vs 53821d3 : +29 -2
    lab_palette.gd         base vs 31f8c05~1 : IDENTICAL   base vs 53821d3 : +75 -0

**Left behind on purpose.** V27's lab also shipped `diorama_chamber`,
`industrial_chamber` and eight diagnostic marker and probe profiles. Those are a
lab's rejected concepts and its instruments; the brief asks for one hall.
`index.json` gains four entries - the `extends` chain of
`contained_hall_v272` - and nothing else. V27.1's changes to `racer_visual.gd`
and `sloped_race_scene.gd` are not taken either: the racers and Race #1 are not
among the three things being integrated.

---

## 3. What had to be wired, and the three decisions inside it

`race2_scene.gd`'s own header promised that "a contained stage will drop in
through the same seam". It does not, and the reason is worth recording because
it is not a bug in either half.

**`course_world.build` is the backdrop and only the backdrop** - sky masses,
cloud band, aurora. The architecture a contained profile authors lives in the
profile's `world` section, and the only code that has ever built that section is
`course_machine.gd`, which is Race #1's machine builder. So
`--environment=contained_hall_v272` on Race #2 used to deliver the hall's sky,
fog, grade and lights **over an empty void**: a contained profile erases the
outdoor backdrop and there was nothing to replace it with.

Three decisions were taken in wiring it, each of which bounds the change.

**3.1 Only the five stage keys are built.** `deck`, `shell`, `pylons`,
`canopy`, `bays`. The eleven terrain-anchored features are skipped, because
every one of them is sited against a heightfield and Race #2's course does not
stand on one. This costs the hall nothing - `contained_base` nulls all eleven
anyway - and it buys the comparison its control: `aurora_valley_v26` authors no
stage, so it reaches `world_cfg.is_empty()` and adds nothing.

**3.2 The room is placed, because the profile cannot place it.** The hall
carries absolute heights: a deck at y = -80, walls footed at -96 and -100. Those
are the terrace and the basin under Race #1's *finish*, and Race #2's course
does not descend a mountainside. The stage is therefore translated by one rigid
lift, derived from the two courses' own numbers:

    datum = max over deck rings of (y + thickness/2)          = -71.50
    lift  = (lowest point of the racing line - 2.0) - datum   = +68.90

The datum is the **top** of the tallest ring rather than its underside because
`environment_stage._deck` refuses a ring whose top would stand above the ground
under it - correctly, since a plate floating over a hillside is exactly the
artefact that test exists to catch. On a flat floor that test becomes a
constraint on where the floor goes, and a floor one unit lower silently deletes
the upper terrace.

**No scale is applied.** A translation is a placement; a scale would be a
redesign of a locked hall. That the room comes out too large for this course is
this branch's headline finding, and the only honest way to report it is to
render the room at the size it was authored.

**3.3 The inherited lens keep-out is dropped.** The 78 points a contained
profile carries are decimated *Race #1* camera paths. Applying them here would
cull hall segments at positions no Race #2 lens ever visits - a room with holes
in it for reasons belonging to another film. The room is built as authored and
the occlusion question is answered from the frames instead (section 6.4, and the
answer is that nothing is occluded).

### 3.4 A pre-existing bug this uncovered: Race #2 never applied a profile's palette

`course_scene.gd:176` calls `EnvBuilder.apply_palette`. `race2_scene.gd` never
did. That did not show while Race #2 only ever drew a backdrop, because the
overrides name world surfaces and Race #2 built none of them. It shows the
instant a stage is built, and it matters most for the edition being integrated:
**V27.2's entire delta is one leaf of that table** - `hall_panel_dark.specular`,
0.5 → 0.06 - so without the call, the merge correction that names the edition is
not in the picture at all. Nor are the hall's ten authored albedos, roughnesses,
`soft_light` backlights and `floor_lift` emissions.

The call is added. It is a correction rather than a regression, and it is not
free: the V26 chain resolves to **46 palette overrides**, all of them world and
backdrop surfaces, so the outdoor control's *backdrop* changes. Measured at
t = 6.00 s:

| | before | after |
|---|---|---|
| pixels differing | | **50.26%** |
| largest change | | **16 / 255** |
| mean frame luma | 24.08 | 22.04 |
| bounding box of the change | | y 0-1353, the backdrop |

No machine or racer material is in that table, and the change is confined to the
rock. **Both sides of every comparison in this document were rendered after the
fix**, which is the principle `tools/race2_cine_render.py` states for its own
control: a comparison in which the control went through a different renderer
measures the renderer.

---

## 4. The locks, verified

| lock | verified by |
|---|---|
| hero seed 8, race physics | `events_switchyard_8.json` regenerated **byte-identical but for `wall_seconds`** |
| SWITCHYARD geometry, mechanisms | 11 runs, 7 modules, 40 actuators, 25 420 triangles; `course.length` 176.516 |
| camera A shot structure | four shots, three hard cuts, `release / upper / middle / run_in` |
| runtime 19.15 s | track `duration` 19.15; both films 1150 frames at 60 fps, 19.167 s |
| zero temporal omissions | every shot's stamps step 1/60 to within 1e-6; each shot starts where the last ended; rendered frame indices 0-1149 with no gaps |
| final sprint | `run_in`, 12.683 → 19.15 = **6.47 s, zero cuts** |
| active pack, smoothing | `race2/rig.py`, `race2/spine.py`, `race2/flow.py` untouched; `flow_A.json` regenerated byte-identical |
| `contained_hall_v272` geometry/materials | profile chain and every radius asserted in the tests; no profile edited |

Re-solving camera A reproduced V28.1's published numbers exactly: 4 shots,
3 cuts, mean 4.78 s, longest 6.78 s, worst reacquisition 0.285, 0 direction
flips, racers 77-95 px, flow score 85.5.

The stage census, printed by the scene on every contained render:

    stage: contained_hall_v272 lift 68.90 floor -0.60 datum -71.50 centre (0.00, 0.00)
    stage: census deck 61, shell 303, pylons 71, bays 0

---

## 5. The mechanism: the hall is a rim, not a room

This is the one paragraph a later art pass needs.

**Camera A never looks above 9.2 degrees below horizontal.** It is a chase
camera that rides the course; its aim sits 33 to 40 degrees below horizontal and
the *top edge* of its frame ranges from -41.98 to -9.23 degrees over the whole
film. It never sees sky, and it never sees anything standing above it.

**Everything the hall puts below that lens is an annulus with an 88-unit hole in
the middle of it.** The deck's inner radius is 88.0; SWITCHYARD's plan reach
from the chamber axis is **27.06**. The nearest standing element, the inner
pylon ring, is at 64.0.

| | layout units | vs the course |
|---|---|---|
| course plan reach | 27.06 | 1.00x |
| inner pylon ring | 64.0 | **2.37x** |
| deck inner radius | 88.0 | **3.25x** |
| lower wall | 92.0 | 3.40x |
| main wall | 122.0 | 4.51x |

So the camera spends the film looking down through the hole where the floor
should be:

| shot | eye y | eye r | aim elev | frame top | centre ray meets the floor plane at r | inside the hole |
|---|---|---|---|---|---|---|
| `release` | 44.9 | 15.7 | -35.4 | -19.5 | 69.8 | **100%** |
| `upper` | 34.1 | 10.4 | -33.2 | -15.9 | 51.8 | **100%** |
| `middle` | 25.6 | 21.0 | -36.2 | -18.9 | 22.2 | **100%** |
| `run_in` | 15.8 | 39.2 | -39.7 | -21.4 | 22.1 | **100%** |

**On 100% of frames the centre ray passes inside the deck's inner radius.** The
only hall the camera catches is the band of wall standing above the lens, and
that band shrinks as the eye descends from 44.9 to 15.8 - which is precisely the
blackness curve in section 6.

The signature of that is unmistakable in the frames: the void fills **from the
bottom of the picture upward**, because the bottom of the frame is the steepest
ray and reaches the hole first. Share of each vertical third that is black:

| shot | top | middle | bottom | outdoor, all three |
|---|---|---|---|---|
| `release` | 7.69% | 17.12% | **83.89%** | 0.00-1.04% |
| `upper` | 12.48% | 36.79% | **94.36%** | 0.00-0.06% |
| `middle` | 32.09% | 75.48% | **98.36%** | 0.00% |
| `run_in` | **80.55%** | **92.71%** | **99.20%** | 0.00-0.11% |

Every column rises monotonically and the bottom row is always the highest. The
outdoor control is at zero everywhere, in every shot. The upper background is
the only part of the room that is never missing; what is missing is everything
under the machine, from the first frame.

The deeper statement: in Race #1 the floor under the machine is *the course's own
heightfield*, built by `course_machine.gd`, and `environment_stage._deck`'s own
docstring says the deck exists to turn that heightfield "into a landform set
into a deck". The hall supplies a **perimeter**, not a floor. Race #2 has no
heightfield, so the hall has nothing to enclose and the perimeter is all there
is.

### 5.1 The three authored bays build nothing

`contained_hall`'s bays are sited on nodes named `split`, `merge` and `finish`.
Those are Race #1's. SWITCHYARD's nodes are `studs`, `drum`, `sweep`, `pair`,
`last`, `start` and `runout` - **disjoint**. `environment_stage._bays` skips a
site whose node is absent, so the three pieces of architecture authored closest
to the action contribute nothing, and the scene now says so out loud:

    stage: bay 'split' wants node 'split', which this course has not
    stage: bay 'merge' wants node 'merge', which this course has not
    stage: bay 'finish' wants node 'finish', which this course has not

This is a finding, not a fault: a bay is authored against a race moment, and
these are a different race's moments.

---

## 6. The measurements

Ten samples a second over both delivered 1080x1920 60 fps films. Environment
coverage is measured by subtracting a **silhouette matte** - the same camera,
the same frames, the world switched off and the background cleared to black -
so a lit pixel in the matte is a pixel of machine or racer. Its own check is
that machine coverage is the same geometry seen by the same camera in both
worlds and therefore has to agree: **6.22% against 5.94%** over the film, and
per shot to within 0.02 on three of the four - `upper` 7.82 against 7.80,
`middle` 6.20 against 6.20, `run_in` 3.20 against 3.19. The fourth, `release`,
differs by 1.29 (9.15 against 7.86), and the reason is worth knowing before
trusting the other numbers: the contained world lights the machine less, so some
of its own edges fall under the 0.5-luma threshold the silhouette is cut at.
The effect is to *under*-count machine and over-count void in the hall, which
means the blackness below is if anything a slightly kind figure.

### 6.1 Coverage

| | outdoor | contained |
|---|---|---|
| void (nothing drawn) | **0.07%** | **64.89%** |
| environment | 93.71% | 29.19% |
| machine and racers | 6.22% | 5.94% |
| mean luma | 23.28 | 12.32 |

| shot | void, outdoor | void, contained | luma, contained |
|---|---|---|---|
| `release` | 0.37% | 36.23% | 19.49 |
| `upper` | 0.03% | 47.88% | 21.90 |
| `middle` | 0.00% | 68.64% | **8.27** |
| `run_in` | 0.04% | **90.82%** | **2.14** |

### 6.2 Which surfaces are in the film

The hall was rendered a third time with every material key painted a flat,
unshaded, unfogged hue and the grade neutralised, and the frames segmented by
exact colour with the machine masked out by its own silhouette. The two
instruments agree: **29.079%** of the film from the marker against **29.19%**
from the matte subtraction.

| surface | `release` | `upper` | `middle` | `run_in` | film |
|---|---|---|---|---|---|
| `hall_panel` | 32.53 | 24.54 | 10.19 | 2.00 | **15.01** |
| `hall_panel_dark` | 9.93 | 7.23 | 10.59 | 2.96 | **6.93** |
| `hall_rib` | 12.96 | 11.47 | 2.37 | 0.66 | **6.28** |
| `hall_deck` | 0.33 | 0.90 | 1.95 | 0.39 | **0.86** |
| `hall_trim` | 0.00 | 0.00 | 0.00 | 0.00 | **0.00** |
| `hall_deck_dark` | 0.00 | 0.00 | 0.00 | 0.00 | **0.00** |
| `hall_glass` | 0.00 | 0.00 | 0.00 | 0.00 | **0.00** |
| `hall_beam` | 0.00 | 0.00 | 0.00 | 0.00 | **0.00** |
| `hall_grate` | 0.00 | 0.00 | 0.00 | 0.00 | **0.00** |
| `lit_hall_warm` | 0.00 | 0.00 | 0.00 | 0.00 | **0.00** |
| `lit_hall_cool` | 0.00 | 0.00 | 0.00 | 0.00 | **0.00** |
| **all hall** | 55.73 | 44.14 | 25.09 | 6.02 | **29.08** |

**Four surfaces carry the room.** Of the eleven keys in the `hall_*` family,
`contained_hall` authors geometry for ten - it never names `hall_grate` - and
**six of those ten never reach the film**: `hall_trim`, `hall_deck_dark`,
`hall_glass`, `hall_beam`, `lit_hall_warm` and `lit_hall_cool`. `hall_trim` is
authored eight separate times, as the cornice and plinth of every band, and is
at 0.000%. Both lit practicals are in the six, which is why nothing in the
picture is warm.

**The trick this needed.** `unshaded` and `no_fog` are not enough on their own.
The grade - an ACES tonemap at exposure 0.81 against a white of 12, then a
contrast and a saturation lift - runs on the *frame*, after shading, so a marker
hue reaches the file as some other colour. Measured before the grade was
neutralised in the marker: eleven surfaces, **0.004%** of the film between them,
against a coverage of 29.19% that is provably there. A V27-era marker profile
does not carry a grade override, so this is a trap any later pass reusing that
mechanism on this room will hit.

### 6.3 The racers

Picked out of each world's matte by saturation, then read out of the delivery.

| shot | outdoor luma | contained luma | outdoor sat | contained sat |
|---|---|---|---|---|
| `release` | 101.03 | 106.46 | 0.752 | 0.716 |
| `upper` | 125.71 | 126.29 | 0.844 | 0.810 |
| `middle` | 112.69 | **63.27** | 0.853 | 0.909 |
| `run_in` | 128.32 | **21.01** | 0.782 | 0.949 |

From the 15.82 s crossing to the end: **119.41 mean luma outdoor, 20.98
contained**, worst frame 16.44. The racers are geometrically visible - camera A's
own metric is 96.7% winner-visible and that is a property of the camera, which
this branch did not touch - and tonally they are not there. The payoff is the
worst-served moment in the film.

### 6.4 Occlusion, parallax, and the title band

**Occlusion.** Hall geometry drawn in front of the machine's own silhouette:
**0.105% of it on average, 3.72% on the worst single sampled frame (t = 8.50)**.
Nothing blocks the racers. This is the one review question the hall passes
outright.

**Parallax.** Mean absolute luma change per 0.1 s over background pixels:

| shot | outdoor | contained | ratio |
|---|---|---|---|
| `release` | 10.53 | 9.72 | 0.92 |
| `upper` | 8.54 | 6.61 | 0.77 |
| `middle` | 8.74 | 2.96 | 0.34 |
| `run_in` | 8.21 | 1.22 | **0.15** |
| film | 8.69 | 4.45 | 0.51 |

The room adds **less** motion than the world it replaces, and the shortfall
grows monotonically through the film. A wall at radius 92 seen from a lens at
radius 10-40 barely moves; V26's foreground rock is much nearer the lens.

**The title band.** Race #2 has no overlay system - PICK A COLOR is a Race #1
and V24 device and does not exist in this pipeline - so this is a measurement of
the picture such a plate would have to be legible over, in the band V24 used
(baseline 269, 71 px cap, 798 px measure), over the first 1.05 s:

| | luma | sd | worst sd | share over 128 |
|---|---|---|---|---|
| outdoor | 22.10 | 12.48 | 32.34 | 0.058% |
| contained | **17.00** | **11.60** | **17.87** | **0.000%** |

The hall is a measurably *better* plate: darker, flatter, and with nothing
bright anywhere in the band. It is the room's one clear win.

---

## 7. The review, question by question

### Hook (0.00 - 2.23)

**Do racers stay dominant?** Yes, and this is the hall's best stretch. 55.7%
hall coverage, racers at 106.5 luma against the outdoor control's 101.0 -
slightly *better* than outdoor. The near wall behind the start is the one place
the room does what it was built to do.

**Is the upper background too heavy?** It is heavy, and it is not the problem.
Across the hook the top third of the frame is **7.7% black** and the bottom
third is **83.9%**. The room's whole weight sits in the one part of the frame
that has any, and there is close to nothing at the other end.

**Is PICK A COLOR clean?** The card does not exist in Race #2. The band it would
occupy is cleaner in the hall than outdoors on all four measures (6.4).

### Early chase (1.80 - 5.20)

**Tunnel or trench?** Trench, and only on one side. The wall is a band across
the upper frame with void beneath it; there is no second wall and no floor to
close a tunnel.

**Does foreground architecture improve speed?** There is no foreground
architecture. The nearest element is the pylon ring at 2.37x the course's own
reach, and parallax is already at 0.77 of the outdoor world by `upper`.

**Occlusion?** None: 0.26% mean over `upper`, 3.72% worst.

### Middle (5.20 - 10.00)

**Does camera A expose giant blank wall faces?** Yes, and this is the clearest
art finding. `hall_panel` alone is 24.5% of `upper` and 10.2% of `middle`, and
the ribs that are meant to divide it are 3.0-3.6 units wide at radius 92-122 -
from a lens 60-100 units away they read as flat vertical bars on a flat plane.
At 1.50 s (`hall_at_1p5s.png`, the hall's own best frame) the entire upper
two-thirds is undifferentiated navy with a single cast shadow as the only
spatial cue.

**Deep or boxed?** Neither: open. 68.6% of `middle` is void.

**Repetitive?** The wall's rhythm is a 32-segment pattern at 11.25 degrees, and
the lens crosses it slowly; but the repetition is not what the eye notices,
because there is not enough of it on screen to repeat.

### Switchbacks (9.60 - 13.60)

**Does architecture help spatial orientation?** No, and it cannot as built. The
three bays that would mark places - `split`, `merge`, `finish` - name nodes this
course does not have and build nothing. What is left is a rotationally symmetric
drum, which by construction carries no information about where along the course
the camera is.

**Do columns or panels block racers?** No. 0.014% mean over `middle`.

### Final sprint (12.68 - 19.15)

**Uninterrupted 6.47 s:** confirmed, zero cuts, frames consecutive.

**Top three readable? Winner visible? Finish bay clean? Payoff background
strong?** The camera delivers all of it - 82.7% top-three, 96.7% winner, 2.92 s
before the crossing - and the room deletes it. The shot is **90.8% black**, mean
luma **2.14**, racers at **21.0** falling to 16.4. There is no finish bay: the
`finish` bay site builds nothing, and 94% of the shot is void or machine. The
payoff background is not strong; there is no payoff background.

---

## 8. The art review

**Premium hall or dark trench?** Dark trench. At its single best frame the room
is flat navy slabs with one cast shadow; at its worst it is absent.

**Contained or claustrophobic?** Neither, which is the surprise. The room is far
too large to be claustrophobic and too incomplete to be containing. It reads as
a distant rim around an open void.

**Reusable or generic?** The *system* is reusable and the *instance* is not. The
material family is disciplined and course-agnostic, and the builder took a new
course with no edits. What does not transfer is every number: the radii, the
absolute heights, and the three bay sites, all of which encode Race #1's course.

**Enough architectural depth?** No. Four surfaces are in the film out of eleven,
there is no foreground layer at all, and the parallax measure says the room
contributes half the outdoor world's motion overall and a seventh by the finish.

**Too much blue or navy?** Yes, and it is measurable rather than a matter of
taste: both lit practicals - the only warm surfaces the family has - are at
**0.000%** of the film. There is no warm pixel in the room anywhere in 19.15
seconds.

**Too many giant flat slabs?** Yes. `hall_panel` and `hall_panel_dark` are 21.9%
of the film between them; `hall_trim`, the family's one light-value edge
surface, is 0.00%. The surfaces that describe an edge are exactly the ones the
camera never sees.

**Is the machine still hero?** In the hook and the upper chase, yes - more so
than outdoors. From `middle` onward, no: not because anything competes with it
but because nothing supports it, and at 21 luma in the sprint the racers stop
being hero by going dark.

**Does the hall add speed through parallax?** No. It subtracts it: 0.51 of the
outdoor world over the film, 0.15 in the final sprint.

**Does it look better in motion than in the V27 screenshots?** No, and the
comparison is not fair to the hall. V27's screenshots are Race #1's camera,
which stands off and looks across a course descending through the room, with a
heightfield filling the floor. Camera A looks down from inside the hole in that
floor. The V27 screenshots are of a different photographic problem.

---

## 9. The environment surfaces that would need a later art pass

Answering the brief's last question exactly. **Not fixed here.**

**In the film, and load-bearing:**

1. **`hall_panel`** - 15.01% of the film, 32.5% of the hook. The single largest
   environment surface. Needs form: it is a flat plane at 60-120 units with no
   modulation, and it is what "giant flat slabs" refers to.
2. **`hall_panel_dark`** - 6.93%. The lower wall at radius 92. Note that V27.2's
   correction is *to this material* and it is now measurably in the picture; the
   correction is sound and the surface still reads as a dark plane because the
   problem here is not its specular.
3. **`hall_rib`** - 6.28%, 13.0% of the hook. The only vertical modulation the
   room has, and at 3.0-3.6 units across from this distance it reads as a
   painted stripe rather than as structure. This is the highest-leverage
   surface: it is what tells a viewer how tall the wall is.
4. **`hall_deck`** - 0.86%, peaking at 1.95% in `middle`, and only ever as a
   thin edge-on band at the top of frame.

**Authored into geometry, paid for, and never on screen** - six of the ten the
hall names:

5. **`hall_trim`** - cornice, plinth, cap; the family's only light-value
   surface, **authored eight times** across the bands. **0.000%.** The surface
   that would describe every edge in the room is the one the camera never sees.
6. `hall_deck_dark` - the outer deck ring and the service level. **0.000%.**
7. `hall_glass` - the clerestory glazing. **0.000%.**
8. `hall_beam` - the pylon braces. **0.000%.**
9. **`lit_hall_warm`** - the bay strips, authored four times. **0.000%.** The
   room's only warm light, anywhere.
10. **`lit_hall_cool`** - the wall slots, authored four times. **0.000%.**

`hall_grate` is the eleventh key in the family and `contained_hall` never names
it, so it is not a surface this hall lost - it is one it does not have.

**Structures that do not exist in this film at all:** the three bay sites
(`split`, `merge`, `finish`), because their nodes are Race #1's.

**The surface that is missing rather than wrong:** there is no floor under the
machine, and no near-field object of any kind inside radius 64.

---

## 10. Environment issues recorded, not fixed

Per the brief, none of these were addressed on this branch.

| # | issue | evidence |
|---|---|---|
| 1 | The hall is ~2x oversized in plan for this course: inner radius 88 against a 27.06 reach | 5 |
| 2 | The deck is an annulus; there is no floor under the machine, and the camera looks through the hole on 100% of frames | 5 |
| 3 | The three authored bays name Race #1 nodes and build nothing | 5.1 |
| 4 | Seven of eleven surfaces never appear; both warm practicals are among them | 6.2 |
| 5 | The final sprint is 90.8% black and the racers fall to 21.0 luma | 6.1, 6.3 |
| 6 | The room supplies less parallax than the world it replaces, worst at the finish | 6.4 |
| 7 | The hall's absolute heights encode Race #1's terrain and need a placement rule wherever it is reused | 3.2 |
| 8 | A V27-era marker profile cannot segment this room: the grade must be neutralised too | 6.2 |
| 9 | Race #2 never applied a profile's palette overrides; fixed here because V27.2 is unrenderable without it, at a measured cost to the V26 backdrop | 3.4 |

---

## 11. Where everything is

The six required outputs, in the order the brief asks for them. Note that (1)
and (3) are **one file**: the V29 Short *is* camera A in
`contained_hall_v272`, and rendering it twice would only prove the renderer is
deterministic.

| # | required output | file |
|---|---|---|
| 1 | full V29 Short | `race2_v29_contained.mp4` |
| 2 | camera A + V26 outdoor control | `race2_v29_outdoor.mp4` |
| 3 | camera A + `contained_hall_v272` | *the same file as (1)* |
| 4 | side by side, outdoor vs contained | `compare/outdoor_vs_contained.mp4` |
| 5 | 270x480 phone | `phone/race2_v29_{outdoor,contained}_phone.mp4` |
| 6 | contact sheet, actual camera A viewpoints | `sheets/camera_A_{outdoor,contained}.png` |

All of them under `exports/race2_v29_switchyard_contained/`. Beyond the six:

| | |
|---|---|
| side by side, per section | `.../compare/outdoor_vs_contained_{1_hook..5_final_sprint}.mp4` |
| section clips, per world | `.../sections/{world}_{1_hook..5_final_sprint}.mp4` |
| surface segmentation sheet | `.../sheets/camera_A_surfaces_marker.png` |
| measurements | `docs/validation/race2/v29_contained/{coverage,surfaces,review}.{json,txt}` |
| the sheets again, and the hall's best frame | the same folder |

All six required outputs are 1080x1920, 60 fps, 1150 frames, 19.167 s, except
the phone versions, which are 270x480 scaled from the delivered files rather
than re-rendered - V28.1's convention, for its reason: a phone proof rendered
natively at 270x480 is a kinder picture than the one being shipped.

`output/` and `exports/` are not in git, per this repository's convention.

To reproduce:

    python tools/race2_camera.py --course=switchyard --seed=8
    python tools/race2_cine.py --seed=8 --only=A
    python tools/race2_v29_short.py all
    python tools/race2_v29_surfaces.py
    python tools/race2_v29_review.py

---

## 12. Tests

`tests/test_race2_v29_contained.py`, 17 tests in three groups - the locks, the
integration, and the findings - with the rendered measurements read from
`docs/validation/race2/v29_contained/` and skipped where they have not been
produced.

The findings are asserted at the values this pass measured, so **a later pass
that fixes the environment will be told by a failing test that it fixed it**.

`tests/test_race2_isolation.py` gained two tests and had one rewritten.
`test_the_renderer_does_not_touch_the_contained_stage` asserted the literal
string `environment_stage` was absent from `race2_scene.gd`; V29 makes that
assertion the opposite of the shipped behaviour. What the test was *for* - that
the scene owns no part of the environment, reimplements none of it and
special-cases no profile - survives intact and is what it now asserts, against
the file with its comments stripped. A second new test asserts the property that
comment-stripping depends on, which is that the scene has no `#` inside a string
literal.

The suites that cover this change - everything matching `race2`,
`environment`, `v23`, `v26` or `v27` - are **590 passed, 16 skipped, 0
failed**, re-run after the fix described two paragraphs down.

The whole repository suite runs **2710 passed, 336 skipped, 10 failed**. Every
one of the ten is accounted for.

**Six are pre-existing and environmental** - one in `test_neon_proof.py`, four
in `test_sloped_v251_world.py`, one in `test_sloped_v252_world.py`. Each raises
`FileNotFoundError` on a path under `output/neon_v11/` or
`output/sloped_race_v1/`; `output/` is gitignored, so those artefacts do not
exist in a fresh worktree. Those three test files are byte-identical to the base
commit and this branch writes nothing under either path.

**Four were this pass's own, and the cause is worth recording.** The four V29
tests that read `review.json` failed in that run because
`tools/race2_v29_review.py --only=bands` was run *while the suite was in
flight*, and `--only=` rewrites the report with just the measures asked for. The
tests were reading a file that had been truncated underneath them. They pass on
the complete report - the file alone is 17 passed - and the lesson has been
folded back in: `_measured` now takes the name of the measure it needs and
**skips** when the report does not carry it, because a partially regenerated
report is a normal state of a working tree and should read as "not produced
yet" rather than as a finding that has changed. Verified both ways: 17 passed
against the full report, 13 passed and 4 skipped against a deliberately
truncated one.

---

## 13. Recommendation

**Do not merge, and do not art-pass this hall for this course.** The defects are
not finish-level. Nothing the room owns stands closer than **2.4x** the course's
own reach from the axis, its floor does not begin until **3.3x** and so never
passes under the machine at all, and its three authored landmarks are placed by
names this course does not use. A lighting or material pass over those facts
would be polish on a building that is the wrong shape.

The two questions worth putting to a brief before any further work:

1. **Should a contained stage be sited from the course, or authored per course?**
   Everything that failed here is a constant the hall carries. A stage that took
   its radii, its floor and its landmark sites as *ratios of the course it is
   given* would have produced a usable room from this same profile.
2. **Does a chase camera want a room at all?** Camera A's frame top never rises
   above 9.2 degrees below horizontal. For that lens the useful environment is
   under and beside the machine, not around and above it - which is the opposite
   of what a hall is.

What is worth keeping from this branch regardless: the seam in
`race2_scene.gd`, which took a whole contained profile with no edit to it; the
palette fix; and the three instruments, which measure any world against any
camera and agreed with each other to a tenth of a point.
