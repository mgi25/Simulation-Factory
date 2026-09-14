# V24: the hook lab

*Prototype. Nothing here is merged and nothing here re-simulates.*

The first uploaded marble-race Short was measured at:

| | |
| --- | --- |
| stayed to watch | 19.6% |
| swiped away | 80.4% |
| average view duration | 24 s |
| length | ~27 s |
| average share viewed | ~89% |

Of the one viewer in five who stayed, nearly all watched it to the end. The race
holds attention once someone commits. **The loss is the first scroll decision**,
and this pass is about the first three seconds and nothing else.

---

## 1. What the shipped opening actually spends its first four seconds on

Measured on the delivered 1080x1920 frame, through `readability.cut_reads` -
the same projection the shipped readability bar uses:

```
OUTPUT  0.000 - 3.500   a course preview: an aerial flight over an empty
                        hillside. No racer is on screen at all
OUTPUT  3.500 - 4.200   the first race frame, frozen, under PICK ONE
OUTPUT  4.200           the film starts moving
```

and the frame that hold freezes:

| | |
| --- | --- |
| racers in frame | 8 of 8 |
| median racer | **81.3 px** |
| pack bounding box | 581 x 124 px, at (353, 1228) |
| share of the frame that is racer, by area | **2.01%** |
| off centre | 0.34 (0.35 of a half-width sideways) |
| the frame is made of | 1.9% racers, 14.7% machine, **56.3% distant hillside, 21.9% sky** |
| everything that is the race | **16.6%** |

A cold viewer's first sight of a racer is **3.5 seconds in, at two per cent of
the frame and frozen** - low and to the left, under a sky and a hillside that are
between them more than three quarters of the picture. The first racer that
*moves* is at **4.47 s**. That is the thing being fixed.

### The one number that turned out to matter

```
distance = 0.5 * extent / tan(fov/2)                    cameras.build_track
px       = 2 * radius / depth / (2 tan(fov/2)) * height  readability.cut_reads
```

At the aim plane `depth == distance` and the tangents cancel:

```
px = 2 * radius * height / extent = 1094.4 / extent
```

**The field of view cancels out entirely.** Widening the lens and standing back
is the same picture; `extent` is the whole of the size control. The shipped start
lens runs it at 14 because 14 layout units is the mixing machine end to end - and
the eight racers span **4.41 layout units**. Framing 14 to show a 4.4-unit
subject is what made the racers dots, and it is the one number this pass moves.
`tests/test_sloped_v24_hook.py` pins the claim by measuring a racer through three
different fields of view at one extent and finding the same size.

---

## 2. What V24 is

One continuous camera move, live from the first frame, that opens tight on the
eight bays and pulls back onto the shipped start lens as the field pours.

```
OUTPUT  0.000           eight racers, large, under PICK A COLOR
OUTPUT  0.117           the release paddles swing
OUTPUT  0.233 - 0.250   the field starts to roll
OUTPUT  1.2 - 1.4       the lens arrives on v221.START's own pose and the
                        shipped start shot carries on, frame for frame
```

There is no course preview and there is no held frame. **Both of the brief's
motion deadlines are met by deleting them, not by speeding anything up**: the
release paddles first stir at replay 0.3167 and production's start window already
opens at replay 0.200, so the mechanism moves 0.117 s into the film for free.

Nothing re-simulates. Seed 5432, the physics, the finish order 5-2-7-4-1-6-3-0,
the course, the obstacle, the chase lenses, the finish and the environment are
exactly what V22.1 ships. The hook consumes replay 0.200 to its handoff and gives
the rest of the start window back to `v221.START`.

---

## 3. The three framings, measured

`bearing` is in the basis `cameras` measures the start lens in: 0 stands
down-course of the aim looking back at the field, 180 stands behind it, and the
shipped start lens opens at 194.

| variant | bearing | elevation | extent | the idea |
| --- | ---: | ---: | ---: | --- |
| `v221` | 194 | 30 | 15.40 | control - the pose the uploaded Short opens its race on |
| `a_rear` | 198 | 26 | 8.2 | A - elevated rear three-quarter, the shipped family tightened |
| `b_gate` | 300 | 30 | 7.2 | **B - front three-quarter across the gate row, under the START sign** |
| `c_column` | 270 | 38 | 7.6 | C - square to the row, eight racers up the portrait frame |

Frame zero, measured. `v221` is the pose the uploaded Short opens its race on,
read off the solved start track rather than retyped - the start lens is written
`bearing=28, elevation=16, extent=14`, `v221.START` overrides two of those and
`cameras.build_track` adds the first orbit and dolly legs before it places
anything, and what comes out is bearing 194, elevation 30, an effective extent of
15.40.

| | `v221` | `a_rear` | `b_gate` | `c_column` |
| --- | ---: | ---: | ---: | ---: |
| racers in frame | 8/8 | 8/8 | 8/8 | 8/8 |
| racers in their own colour | 8/8 | 8/8 | 8/8 | 8/8 |
| the same, at 270x480 | 8/8 | 8/8 | 8/8 | 8/8 |
| median racer | 81 px | 135 px | **146 px** | 140 px |
| smallest / largest | 79 / 84 | 128 / 144 | 130 / 167 | 124 / 162 |
| racer share by area | 2.01% | 5.58% | **6.61%** | 6.12% |
| pack box | 581 x 124 | 961 x 205 | 671 x 482 | 120 x 700 |
| off centre | 0.34 | 0.15 | **0.08** | 0.11 |
| off centre, sideways | 0.35 | 0.03 | **0.00** | 0.04 |
| closest pair, diameters | 0.97 | 0.95 | 0.71 | 0.63 |
| least-visible disc | 0.99 | 0.99 | 0.84 | 0.77 |
| frame is racer + machine | 16.6% | 27.4% | **34.5%** | 32.3% |
| frame is distant hill + sky | **78.2%** | 43.2% | 8.2% | **0.0%** |
| PICK A COLOR, worst twelfth | 8.4:1 | 8.6:1 | 7.8:1 | 8.5:1 |
| mark sits at | y 1574 | y 1651 | **y 269** | **y 269** |
| mechanism moves | 0.117 s | 0.117 s | 0.117 s | 0.117 s |
| racers move | 0.267 s | 0.250 s | 0.233 s | 0.233 s |
| camera moves | never | 0.200 s | 0.167 s | 0.167 s |
| bars failed | **5** | 0 | 0 | 0 |

`v221` here is the shipped *pose*, held, over live footage - a composition
control and not a motion one. The film it is taken from freezes the frame for
0.7 s and puts 3.5 s of empty-hillside preview in front of it, so its real first
racer motion is at output **4.47 s**, not 0.267.

**Recommended: `b_gate`.**

### Why the front angle wins, and why it was not the first guess

The shipped bearing is on the **up-course** side of the bay row, and three
things follow from that which no amount of tightening fixes:

* the module's own backboard stands between the lens and the field. At elevation
  26 all eight racers still read; at 40 seven do; at 54 the board covers the row
  outright and **one of eight** shows its own colour;
* the backdrop up-course is the sunset sky, which is 30.3% of `a_rear`'s frame
  and too bright for warm-white text - `text_plate` puts PICK A COLOR at y 1651,
  *below* the racers, because that is the only plate the frame has;
* the course's **START sign faces down-course**. From behind it is invisible.

Round to the open side and all three invert. The backboard is behind the racers,
so the eight read as whole balls. The backdrop is the massif in its own shade, so
the empty share collapses from 78.2% to 8.2% - and to 0.0% for `c_column` - and
the mark goes back to the top of the frame. And the sign is in the picture - **the cheapest possible statement of
the premise, already built**. No overlay says "this is a race" as fast as a sign
that says START.

And a fourth, which only showed up once the board was measured at the size the
retention numbers were taken at.

### 3.1 The stanchions, and a defect a full-resolution measure passed by one degree

The eight release stanchions stand between a rear lens and the row, and **which
racer one of them is across is a sharp function of the bearing**:

One sweep, one elevation, one pan, scored at both sizes:

| bearing | racers in their own colour, 1080x1920 | at 270x480 |
| ---: | ---: | ---: |
| 194 (the shipped bearing) | 7/8 | 7/8 |
| **198** | **8/8** | **8/8** |
| **202** | **8/8** | **8/8** |
| 206 | 7/8 | 7/8 |
| 210 | 7/8 | 7/8 |
| 214 | 7/8 | 7/8 |

**The window is about six degrees wide, and the shipped bearing is four degrees
outside it.** At 194 the turquoise racer is more than half behind a post; by 206
the next post along has taken a different one.

That narrowness is not the only reason to distrust the rear family. An earlier
pick at 204 - a cell of a coarser sweep - measured **eight of eight at
1080x1920** and only seven at 270x480: the yellow racer's disc read 29.2 degrees
off its own hue at the delivery size, *one degree inside the 30-degree bar*, and
131.4 degrees off at a quarter of it, where the downsample mixes the sliver of
yellow with the navy post it sits on. The full-resolution measure passed a
framing that loses a racer on a phone, which is the size the retention numbers
were taken at.

198 holds all eight at both sizes at every elevation from 22 to 30. It is four
degrees from where the shipped start lens already stands, which makes A's turn on
to the start lens the smallest of the three by an order of magnitude.

Two things follow, and the second is the more useful:

* the grid stage scores at **both** sizes, and so does the report;
* a framing whose legibility turns on four degrees of bearing is a framing whose
  legibility is an accident of where the posts happen to fall. The front ones are
  not - there is nothing between the lens and the row at all - which is why
  `b_gate` and `c_column` hold eight of eight at both sizes in every cell of
  every sweep run in this pass.

`c_column` is the other idea worth keeping: square to the row, the eight project
as a single vertical file, **120 x 700 px against A's 961 x 205**. It is the only
framing that spends the long axis of a portrait delivery on the subject, and the
only one with **zero** distant hillside or sky anywhere in the frame.

---

## 4. Three instrument findings, two of which changed the answer

### 4.1 `sightlines` cannot see the thing that hides the racers

`sightlines.course_solids` builds its occluders from `module.local_colliders()`.
That is the right source everywhere else on this course - a channel's acrylic
guard, the finish gantry and the piers are all collidable - but **the board the
eight racers sit against is drawn and not collided**, because the marbles rest in
cradles and never touch it.

Measured at two framings whose renders show half the row and then the whole row
lost behind that board, `Bundle.first_hit` reports **every one of the sixteen
rays clear** - centre and rim alike, at both.

So visibility at the start is read off the picture instead.
`v24_hook.legibility_report` is `tools/sloped_contrast_measure.separation`'s
measure - a racer's disc against the annulus around it, in CIELAB - with one
column added: the Lab hue angle of the disc against the hue angle of the colour
that racer is supposed to be. The pair separates the two ways of being lost:

```
low dE, any hue      the racer is the same colour as what is behind it
any dE, wrong hue    the disc is not the racer at all - it is the board
```

Hue is taken in Lab and not in HSV: the warm key light moves a rendered candy red
from HSV hue 356 to 36, a 40-degree miss that is not one. In Lab the same two are
34 and 39 degrees off the a\* axis.

And the disc's colour is its **median**, not its mean. A lit ball carries a small
blown highlight, and averaging it in drags the disc toward white and rotates its
hue by up to 30 degrees - which is the whole width of this bar. Switching to the
median immediately found a real defect the mean had been hiding: at the shipped
bearing of 194 the turquoise racer sits **more than half behind a release
stanchion**, reported as a hue 70 degrees off its own. That is why `a_rear` is at
204 rather than 194: swept over bearing and lateral pan, 204 with a pan of -0.2
is the only cell of twelve that holds all eight racers *and* all eight colours.

### 4.2 An exact window edge resolves to the previous window

`sloped_race_scene.replay_at` matches a segment on `out_seconds <= high`, so an
output second sitting exactly on a window boundary resolves to the window
*before* it. The grid harness this pass used to render twelve candidate framings
in one Godot launch asked for frames at `k / 60` - every one of them a boundary -
and got candidate `k - 1` in every tile but the first.

It produced a table that looked like a finding: legibility jumping 8, 1, 2, 2, 2,
3, 0, 4, 4, 1, 6, 6 across a smooth sweep of elevation, which reads as a hard
occlusion threshold somewhere near elevation 24. There is no such threshold. With
the samples moved to `(k + 0.5) / 60` the same sweep is **8, 8, 8, 8, 8, 8, 8, 8,
8, 8, 8, 8**.

The delivered tracks are not affected - the hook's shared boundary row exists
precisely so both readings are the same pose, which is the shipped
`course_preview.preview_track` convention - but any *sheet* rendered by output
second has to ask for a window's middle.

### 4.3 The bar the machine could never have passed

The first version of this module required the closest pair of racers on screen to
be 1.15 diameters apart. **The eight bays are 4.41 layout units end to end, which
is 0.63 between neighbours against a racer diameter of 0.57 - 1.105 diameters,
centre to centre, in the geometry itself.** No lens could ever have passed it,
and the shipped opening's 0.97 is already 88 per cent of the ceiling.

Worse, the measure was answering the wrong question. It failed `b_gate` at 0.73
and `c_column` at 0.64, and the renders of both show eight separate balls in
eight separate bays, unmistakably - because a row seen down its own axis stacks
in *depth*, and two centres half a diameter apart are a row in perspective rather
than two balls in a heap.

`disc_visibility` asks the question directly instead: the eight discs are
rasterised in depth order and each racer keeps the share of its own silhouette no
nearer racer is standing on. The shipped opening and `a_rear` lose nothing at all
(1.00, the row being broadside to both), `b_gate` keeps 0.86 and `c_column`,
which stacks the row hardest, keeps 0.77. Spacing is still reported, because it
says whether the row is being seen broadside or end-on, but it is a diagnostic
and not a bar.

The consequence for the brief: **"strong colour separation" cannot be bought with
spacing.** The ceiling is the machine's. It has to come from size and from each
racer's own colour being on screen.

---

## 5. The handoff

The hook lands on `v221.START`'s own first pose and the shipped start shot
carries on. Two things make that a join rather than a cut.

**The last row is shared.** The hook cut carries one row past its own last
rendered frame - the first row of the start cut - and its `to` is that row's
time, which is `course_preview.preview_track`'s convention and exists for the
boundary-resolution behaviour in 4.2. The test asserts equality of the row, not a
tolerance.

**Every scalar lands on a cubic Hermite with a matched end slope.** A smoothstep
arrives with zero velocity, and the shipped start shot is not at rest at its
first frame - its orbit and dolly legs are already ramping. So each of bearing,
elevation, reach, field of view and the three aim axes lands on a curve with
`h(0)=0, h'(0)=0, h(1)=1, h'(1)=g`, with `g` solved from the start shot's own
first-frame rate:

```
g = rate_start * duration / (land - open)
```

so the lens arrives moving at the speed the next shot is already moving at.

| variant | turn | lens step at the join | largest step inside the shots | field of view |
| --- | ---: | ---: | ---: | ---: |
| `a_rear` | 4 deg over 1.20 s | 0.084 | 0.254 | 0.00 |
| `b_gate` | 106 deg over 1.40 s | 0.036 | 0.648 | 0.00 |
| `c_column` | 76 deg over 1.30 s | 0.028 | 0.498 | 0.00 |

Every join moves the lens **less than the shots move it themselves**, which is
the only fair yardstick - and under a thirtieth of `cameras.MAX_CAMERA_STEP`.

### The one thing to watch on the clip rather than on the table

The reveal is by a long way the fastest camera move in the film. The shipped
V22.1 start moves its lens at most **0.057 layout units a frame** across both its
windows; `b_gate` peaks at 0.648, which is eleven times that - inside
`cameras.MAX_CAMERA_STEP` of 1.2, but not by the margin every other shot on this
course sits at. It is a deliberate whip and it may read as one. The trade is
bought with hook length and nothing else:

| variant | hook | turn | peak lens step | degrees a second | landing error |
| --- | ---: | ---: | ---: | ---: | ---: |
| `a_rear` | 1.20 s | 4 | 0.254 | 3.3 | 0.084 |
| `b_gate` | 1.40 s | 106 | 0.648 | 75.7 | 0.036 |
| `b_gate` | 1.60 s | 106 | 0.559 | 66.2 | 0.029 |
| `b_gate` | 1.80 s | 106 | 0.491 | 58.9 | 0.023 |
| `c_column` | 1.30 s | 76 | 0.498 | 58.5 | 0.028 |
| `c_column` | 1.70 s | 76 | 0.372 | 44.7 | 0.018 |

**1.85 s is a hard ceiling** and `start_plan_for` raises rather than silently
clipping: `v221.START`'s first window ends at replay 2.050, and a hook that ran
past it would be eating into the rotor omission rather than into the shot in
front of it.

### The orbit the hook has to absorb

`v221_shuffle.plan_legs` hands each start window the share of the whole shot's
orbit that its own *length* earns, so that the rate never changes across the
rotor omission. That is right for a plan whose two windows are the whole shot and
wrong the moment a hook eats the front of it: moving `live_from` from 0.200 to
1.400 makes the first window a third of its length, and the solver then spends
the same 36 degrees over the shorter remainder. Measured before the fix, that
moved **every frame of the shipped start shot after the handoff** - up to 4.05
layout units in the first window and 3.19 in the second, across all 163 frames of
the post-omission window.

`start_plan_for` writes the legs out instead and moves only the first one's near
end, to the value the shipped ramp already had at the handoff:

```
orbit_low' = low + (high - low) * (handoff - 0.200) / (2.050 - 0.200)
```

After that, every replay frame the shifted plan still shows is the pose
`v221.START` shows at the same replay second, to four decimal places - the
equality the test pins. **The hook replaces the first N frames of the start shot
and touches nothing else.**

---

## 6. The mark

`PICK A COLOR`, not `PICK ONE`. Twelve glyphs against eight: at
`overlays.pick_one`'s own 150 pt with the same tracking the line runs past both
edges of a 1080 frame. At 96 it is 798 px, a thirteen per cent margin each side,
and 71 px of cap height - **17.8 px at the 270x480 a feed scrubs at**.

It is drawn through `overlays._shadowed`, so the face, the tracking, the warm
white and the soft shadow are the film's own and cannot drift from it. What is
*not* inherited is the baseline: `overlays.pick_one` has 395 frozen into it,
measured against V20's held opening frame whose racers sat at y 831-887. This
opening does not put them there, so the baseline is an argument.

`text_plate` scores every candidate baseline on the rendered frame, in twelve
columns - one per glyph - and takes the **worst** column. A mean cannot say which
letters are readable: the first version of this scored the plate on its mean
colour and its luma spread and rejected two framings of three for "crossing a
seam", which was true and useless, because it could not then say where to put the
mark instead.

| variant | baseline | worst twelfth | mean | cap on a phone |
| --- | ---: | ---: | ---: | ---: |
| `v221` | y 1574 | 8.4:1 | 9.6:1 | 17.8 px |
| `a_rear` | y 1651 | 8.6:1 | 10.0:1 | 17.8 px |
| `b_gate` | y 269 | 7.8:1 | 12.6:1 | 17.8 px |
| `c_column` | y 269 | 8.5:1 | 11.0:1 | 17.8 px |

The two front framings put the mark at the top of the frame, where a portrait
composition is read first. The two rear ones cannot: the sky above the racers is
too bright for warm white, so the mark is driven below them.

No leaderboard, no flags, no names.

---

## 7. The bar

`v24_hook.check_hook`. Every threshold is set from a measurement.

| | bar | why |
| --- | --- | --- |
| racers in frame | 8 | fewer and the premise is not on screen |
| median racer | >= 110 px | a third again of the shipped 81.3 |
| least-visible disc | >= 0.55 | a little over half a ball; see 4.3 |
| off centre | <= 0.22 | a third of `readability`'s shipped bar |
| off centre, sideways | <= 0.22 of a half-width | `off_centre` under-reports a sideways miss by 16/9 |
| racer share by area | >= 4.0% | double the shipped 2.01% |
| hillside and sky | <= 45% | the shipped opening is 78% |
| racers in their own colour | 8 of 8 | measured on the render; see 4.1 |
| PICK A COLOR, worst twelfth | >= 3.0:1 | WCAG large text |
| first movement | <= 0.30 s | the brief's own ask |
| handoff | under the largest step inside the shots | a join nobody can find |

All three variants pass every one. The control fails five.

---

## 8. What this pass deliberately did not decide

* **the total shuffle duration.** The hook is 1.2-1.4 s and the rest of the start
  is V22.1's, including the 116-frame rotor omission. Whether the mix should be
  shorter is a separate question with its own evidence;
* **the rest of the film.** Not one frame after the handoff is different;
* **whether to keep a course preview anywhere.** The brief says the opening may
  not be one. It does not say the film may not end with one.

## 9. Reproducing

```
python tools/sloped_v24_hook.py --stage all --godot PATH
python -m pytest tests/test_sloped_v24_hook.py -q
```

Stages are `solve`, `frames`, `measure`, `render`, `sheet`, `report`. `solve`
needs only the replay; `measure` needs `frames` to have run, because two of the
brief's questions can only be answered from the picture.

The search the three came out of is a stage too, so the choice can be re-run
rather than only asserted:

```
python tools/sloped_v24_hook.py --stage grid --grid-name rear_pan \
    --grid "bearing=184,194,204:elevation=26:extent=8.2:pan=-0.6,-0.2,0.2,0.6"
```

It renders and scores the product of the axes in **one** Godot launch, which is
possible because the machine holds still between replay 0.083 and 0.300 - after
the solver has settled the field into its bays and before the paddles stir. That
is fourteen frames, and fourteen is the ceiling on a single sweep.


Boards land in `docs/validation/sloped_race_v1/v24/`, clips and tracks in
`output/sloped_race_v1/v24/` - which is generated output and not in the branch.

In the branch:

| | |
| --- | --- |
| `first_frames_phone.png` | **the product**: all four first frames at 270x480, with the mark |
| `first_frames_phone_plain.png` | the same four without it |
| `first_frames.png`, `_plain` | the same two at a third of the delivery |
| `motion_<variant>.png` | the first 1.3 s of each, at 270x480: 0.000, 0.117, 0.250, 0.500, 0.900, 1.300 |
| `grid_rear_bearing.png` | the six-degree legibility window of section 3.1 |

The proof clips - `open_<variant>.mp4`, 3.6 s each, the hook plus enough of the
start shot to read the handoff - are in `output/` and are not.
