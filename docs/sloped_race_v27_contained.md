# V27 — the contained stage

Three enclosed environments for the sloped race, measured against V26's outdoor
canyon through V24's own camera track. A lab pass: nothing here is integrated
and nothing here ships. The recommendation is at §18 and the weaknesses that
would have to be closed first are at §19.

    branch     v27-contained-environment-lab
    baseline   origin/main @ eaca65e (V26 accepted production)
    seed       5432, untouched
    profiles   contained_base, contained_hall, diorama_chamber,
               industrial_chamber, and four diagnostic markers

---

## 1  Motivation

V26 is the accepted production edition: V24's format, V25.2's stylised valley,
V23B's machine, 20.117 s. Its world is *functional and improved* and this pass
does not dispute that. What it tests is a different philosophy, asked for in
the brief:

> keep viewer attention on machine and racers · reduce distracting landscape ·
> create a reusable stage for many future videos · maintain strong 3D depth ·
> give consistent brand identity · allow many race/course themes without
> rebuilding a full outdoor world

The channel's next stages are country skins, a second course and other
simulation machines. Each of those needs a world; each of those, under V26's
arrangement, would need a *landscape*, authored against that course's own
sightlines. A stage is the alternative: one room, reused, that a new machine is
installed in rather than dropped into.

So the question this pass answers is not "is a room prettier". It is:

1. does a contained environment cost the race anything measurable, and
2. is what it buys worth what it costs.

---

## 2  Why a contained environment at all

V26's world is 2284 mesh instances and 651k triangles, of which the near
field - boulders, scarps, spires, trees, patches - is the great majority. The
marker segmentation says how much of the picture that near field occupies:

    band cover, mean over the twelve proof moments

                     near ground   near structure   mid band   far wall
    V26 outdoor            9.4%           36.9%       14.7%       7.5%

Thirty-seven per cent of every frame is rock and vegetation immediately beside
the track. That is V25's deliberate contribution and it is what makes the
valley read as a place. It is also, in a nine-by-sixteen frame at 270 px wide,
thirty-seven per cent of the picture that is not the race.

A contained stage inverts the distribution: the landform stays (it is the
course's own heightfield and may not move - see GEOMETRY IS NOT THEME), but
what stands beside it becomes architecture at a *lower count and a lower
frequency*, and the enclosure behind it becomes a single continuous surface
instead of a scatter of masses.

---

## 2.1  Render neutrality, and a reproducibility trap

This pass adds five keys to `environment_world.BUILD_ORDER`, eleven keys to
`lab_palette._build` and a new file that the world builder preloads. None of
that may change a frame of anything shipped before it, and the proof is a
hash rather than an argument: three V26 frames were rendered before any code
was written and again after all of it, through the same command.

    out 0.000   8e029f581940e27d   8e029f581940e27d   identical
    out 9.600   788f8a741277e005   788f8a741277e005   identical
    out 17.517  d175f5ab55129898   d175f5ab55129898   identical

`tests/test_sloped_v27_contained.py` carries the machine-independent half of
the same claim - a V26 render's world census must be V25.2's eleven features
and none of V27's five - gated on `$GODOT_BIN` so it skips where there is no
renderer.

**The trap, found while taking that proof.** The first comparison said two of
the three frames had changed, and nothing had. A still is only reproducible
against another still requested in the **same `--at` list**: the renderer
accumulates between samples inside one process, so output second 9.600 asked
for as the second of three and as the fifth of twelve are different images.
Every sheet in this pass is therefore rendered from one twelve-second list per
world, and a future pass comparing against these frames has to ask for the
same twelve.

---

## 3  The universal-stage requirement

Part P of the brief asks, of every decision: would this still be right with
country flags on the racers, a different machine palette, a different course,
six racers instead of eight, a different machine entirely?

Three constraints follow and they are enforced in the data rather than
remembered:

* **Neutral, by value and by hue.** The eleven new material keys are graphite,
  charcoal and cool grey, with exactly two saturated surfaces - a warm and a
  cool lit strip, both dimmer than the machine's own practicals. There is no
  blue world here; `tests/test_sloped_v27_contained.py` checks the keys exist
  and that no machine pass names one.
* **Five builders, not three sets.** `environment_stage.gd` provides `deck`,
  `shell`, `pylons`, `canopy` and `bays`, and all three rooms are those five at
  different numbers. A stage that needed a sixth builder per theme would not be
  a stage.
* **Placed against the race, not against a map.** Every bay is sited from the
  layout's own node table (`start`, `mix`, `obstacle`, `split`, `merge`,
  `finish`), so a site the layout has no node for is skipped and a second
  course inherits the architecture at *its* nodes.

---

## 4  What the camera can actually see

This is the measurement the pass turns on, and it rebuilt all three concepts
after their first render. `tools/sloped_v27_contained.py --stage envelope`
reads the solved camera track and nothing else, and reports the highest point
at each plan position that lies inside any V26 frame.

    r   |    0    30    60    90   120   150   180   210   240   270   300   330
    ----+------------------------------------------------------------------------
     30 |   25    29    26    35    40    42    46    47     -     -    24    22
     50 |   14    15    21    33    37    39    44    60     -     -     -    14
     70 |    3     4    24    32    34    33    40     -     -     -     -     6
     90 |   -8    -6    20    28    27    31    35     -     -     -     -    -2
    110 |  -18   -14    15    24    22    27     -     -     -     -     -   -10
    130 |  -26   -21    11    21    18    22     -     -     -     -     -   -17
    160 |  -37   -32     4    16    11    16     -     -     -     -     -   -29

    camera eye height      19.3 to 66.1
    the top of frame is always at least 4.7 degrees BELOW horizontal
    never in any frame     bearings 225-255 and 270-285

Three things fall straight out of it.

**A ceiling over the machine is invisible.** These cameras stand at elevations
of 30 to 54 degrees against vertical fields of 34 to 36, so the top edge of
every frame is below horizontal - at its shallowest, 4.7 degrees, at replay
14.02 in the second obstacle cut. Nothing above a camera's own eye height is
ever in shot, at any radius. §11 is what that did to the canopy.

**The wall has to reach +29 at radius 120 and no higher.** That is the highest
the top of frame gets at that radius, and it is what set concept A's main
course at +26 with a string course on it, so the one architectural line the
hook frame can see is a deliberate one rather than the top of a wall.

**A third of the compass is never photographed.** Bearings 225 to 285 are
outside every frame at every radius, and past radius 110 only 315 through 195
is in shot at all. All three concepts still build a full ring at their outer
radius: the saving is real and it is *not taken*, because a stage that only
walls the arc this camera track happens to use is not a stage. The measurement
is recorded so a future pass under a fixed camera can take it.

## 4.1  Where architecture can stand

`--stage sites` searches every position within 40 units of each race node for
one that is 10 units clear of the racing line, 16 clear of the camera path,
inside that section's own frustum, and further from the camera than the node.

    node        viable   best site                     ground   ceiling  headroom
    obstacle         0   -                                  -         -         -
    split           81   offset [+36,+6] bearing  80.5   -23.7     +30.2      53.9
    merge          184   offset [+8,+38]  bearing  12.0   -35.8      +4.4      40.3
    finish         376   offset [+32,+20] bearing  59.5   -74.2      +2.6      76.8
    start           67   offset [+10,-38] bearing 165.3   -47.5     +38.2      85.7

**The ground behind the race has already fallen away.** `course_terrain` fades
from the racing line to `edge_y` at −82 between radius 58 and 94, and every
place a camera can see *past* the machine is out in that fade. So the recessed
bay beside the track that Parts M, N and O describe - and that all three
profiles were first authored with - cannot exist here: there is no ground
beside the track to recess into. What stands at those sites is a tall structure
rising out of a pit, 40 to 85 units of it, of which the frame shows only the
top.

**The obstacle has no viable site at all.** Not one position within 40 units of
it is legal, in frame and behind the action: the camera runs along the course
there and the course is the whole frame. §12 is what was done instead.

---

## 5  Concept A — Premium machine hall  (`contained_hall`)

A drum in two courses, a lower wall under it, and a nearer wall behind the
start.

    main wall       radius 122, 32 segments at 11.25 deg, foot -100, top +26
                    rhythm: panel rib glass bay panel rib panel slot
    clerestory      radius 122, 32 segments, foot +26, top +56
                    rhythm: panel slot; its plinth is the string course at +26
    lower wall      radius 92, 24 segments, foot -96, top +4
                    an explicit 24-entry rhythm; bays at indices 1, 2, 3
    start backdrop  radius 90, bearings 150-210, foot -96, top +38
    deck            88-124 at -80, 122-154 at -74, plus a finish landing
    columns         16 at radius 80 (82 tall, braced), 12 at radius 64 (54)
    overhead        none - see §11

    1513 meshes · 540,440 triangles · 352 ms/frame

The wall's eight-step rhythm repeats four times round, so a viewer can count it
and read the room's size off the count - which is what a rib is for, and the
reason a wall with nothing on it is unreadable at any distance. The bays are
the only places a practical washes a surface without touching the machine, and
the four dark-glass segments are the brief's "occasional translucent panels" at
a count that keeps *occasional* true.

**The clerestory is load-bearing rather than decorative, and only just.** Its
own panels sit at +26 to +56, which the envelope (§4) puts above the top of
frame at almost every bearing - so what a viewer sees of it is its *plinth*,
the continuous light-value string course at +26, exactly where the top of the
hook frame passes through at that radius. The band above that line exists
because the main course alone tops out at +26 and the measurement asks for
+29: without it the hook leaks sky.

The **start backdrop** is the one band that exists for a single shot. The start
sits in a cut on the uphill side and the hill behind it stands at +40 at radius
60, so the only background frame 0 has is the strip above that ridge - bearings
150 to 210 - and a wall at 122 is 120 units away in it. This one is at 90 and
tops out at +38.

Mood: expensive, clean, modern, timeless. The most neutral of the three and the
one whose material family would survive the most changes of subject.

---

## 6  Concept B — Toy diorama chamber  (`diorama_chamber`)

Closer, lower, rounder, and with far fewer pieces in it.

    wall            18 segments at 20 deg, radius alternating 104 / 113,
                    foot -96, top +46; rhythm bay panel bay rib
                    fillet 1.8 (A's is 0.7), cornice 5.5, plinth 5.0
    platform skirt  18 segments at radius 79, foot -94, top -46
    start backdrop  5 lobed segments, bearings 152-212, radius 90 / 96
    deck            78-114 at -48 (the display platform), 112-152 at -74
    columns         10 at radius 70 (74 tall), 6 at radius 60 (44)
    overhead        none, by design

    1319 meshes · 498,800 triangles · 356 ms/frame

The two-step radius cycle makes the plan a scalloped ring rather than a drum,
and the heavy cornice and plinth plus the trebled fillet are what carry the
moulded, collector-set read the brief asks for. The landform stands on a broad
display platform at −48 with its own skirt wall under it: an object presented
on a plinth rather than a place you are standing in.

Not childish: the value range is A's, the saturation is A's, and the only thing
that is "toy" about it is that the forms are larger, rounder and fewer.

---

## 7  Concept C — Enclosed industrial canyon  (`industrial_chamber`)

Two tall slabs facing each other across the course.

    left slab       9 segments, bearings 66-162, radius 88, foot -100, top +80
    start slab      4 segments, bearings 174-210, radius 88, same section
    right slab      5 segments, bearings 306-354, radius 88, same section
    back wall       30 segments, full ring, radius 140, foot -100, top +42
    deck            84-116 at -70 (grated), 114-158 at -80 (the shaft floor)
    truss           12 legs at radius 76, 76 tall, braced, each with a lamp
    overhead        3 catwalk members on the left wall's own bearing,
                    radius 56-100 at y +24
    grade           ambient raised a tenth over the shared base

    1324 meshes · 498,212 triangles · 353 ms/frame

The only concept whose *near* enclosure is not a ring: it walls the arc the
cameras actually look across at radius 88 and keeps a plain full ring at 140
behind it, so it takes the shape of the measurement without taking the saving. The one overhead
placement on this course that reads is here - a catwalk crossing in front of
the left slab at radius 56 to 100, inside the measured ceiling of about +30 on
those bearings, out past the far end of the camera path, and above nothing at
all since the course never gets beyond radius 47.

Dramatic and mechanical, and the measurements in §16 are why it is not the
recommendation.

---

## 8  The hook

Every concept renders V26's exact frame 0. PICK A COLOR is measured at V24's
own baseline of 269, on the picture the card will sit on, in twelve columns -
one per glyph - and scored as the *worst* column, unaided by the card's own
drop shadow.

                        V26      A        B        C
    worst column       8.64     8.45     8.40     8.42     (WCAG large: 3.0)
    mean contrast     15.21    15.41    15.41    15.39
    plate luma         30.4     30.3     30.3     30.4
    racers legible      8/8      8/8      8/8      8/8
    least racer dE     65.9     71.7     71.7     71.7
    best baseline       269      269      269      269

**The hook is not damaged and is slightly improved.** The card's own contrast
is unchanged to within a fifth of a ratio in a field where 3.0 is the bar, and
V24's chosen baseline is still the best available in all four worlds - so the
contained stage puts no pressure on the one overlay number this pass is not
allowed to move.

What does improve is the thing the brief ranks first. The eight racers separate
from what is behind them by ΔE 71.7 in the contained stages against 65.9 in
V26, a nine per cent gain, because the background behind the gate row stops
being mottled teal rock and becomes one quiet neutral plane.

What does *not* change is how much architecture frame 0 can show. The hill
fills the upper left and the only background the shot has is a strip along the
top right - 7.6 per cent of the frame in every world, control included. The
start backdrop wall is in that strip and it is the whole of what a contained
stage buys here.

    no enclosure object occludes a racer     confirmed, 8/8 legible
    no bright practical behind the letters   confirmed, plate luma 30.3
    no wall edge is tangent to the text      confirmed, plate variance 41.2
                                             against V26's 39.4

Those are numbers, and numbers cannot see a wall edge landing behind a glyph.
`hook_card.png` is the visual half of the same check: the four frame zeroes at
270x480 with the delivered plate drawn on them by `v24_hook.pick_a_color` at
V24's own baseline, which is the call `tools/sloped_short.py` makes. Nothing in
any of the three stages touches a letter.

---

## 9  Depth and parallax

`--stage parallax` reports two things. The first is a property of the camera
track and is identical in all four worlds: the screen travel of a *static*
point on the view axis, by its distance from the lens.

    move             20u     40u     80u    160u    320u
    descent_run    102.9    52.2   110.5   141.0   156.2
    obstacle_pan    20.0    85.7   136.5   161.9   174.7
    fork_swing      85.8    22.6    19.9    35.8    44.4
    branch_cross   222.7    21.3    85.3   138.6   165.5
    final_dive     172.2   104.1    98.8   103.7   107.7

**The curve is not monotone, and that is the camera language rather than an
error.** These are tracking shots: the camera translates and rotates together
so that the subject stays put in frame, which makes the *subject distance* the
pivot. Parallax is at a minimum there - 20 to 52 px - and grows in both
directions. A contained stage puts its wall at 90 to 200 units, which is in the
high-parallax half of that curve, and its near columns at 20 to 60, which is in
the other one.

The second is what each world does with it: the fraction of each depth band's
screen area that is no longer the same area a tenth of a second later.

                       moves ordered near-to-far
    V26 outdoor        0 of 5
    A                  5 of 5
    B                  4 of 5
    C                  5 of 5

**All three contained stages order their depth bands and the control does
not.** V26's far band is a sliver at the frame edge that the machine eats and
uncovers, so it measures as moving faster than the rock in front of it; its
depth is real but it is carried by one band that is 37 per cent of the frame
rather than by a series.

A caveat on the instrument, and it is a finding about the project rather than
about these walls: **the block matcher this lab inherited from V25 cannot track
either world.** A 41-pixel window of V26's own stylised rock has an L* standard
deviation of 0.1 to 0.5, and a graphite panel has less; the matcher refuses
anything under 1.4 and returns a displacement for one band in three. The
overlap measure above needs no texture, which is why it is the one reported.

---

## 10  Lighting

The base changes five lights and deliberately leaves three alone.

    changed   WorldKey, WorldFill, WorldWarm, WorldRim, WorldBounce  (mask 2)
    untouched Key (mask 1), Rim, ValleyBounce                        (all)

`Key` at energy 2.85 is the machine's, and a pass that claims to change only
the environment may not touch it. So the machine in a contained frame is lit by
the same light as the machine in a V26 frame, and "only the environment
changed" is a property of the profile diff rather than a claim in this report.

The interior rig is a steep soft key from over the wall behind the start, a
cool fill from the opposite side, one warm term raking *along* the wall rather
than across it, a rim for edge separation and an up-light from the deck.

Two rows of the grade matter more than the rest:

* **ambient_sky_contribution 0.08 with an explicit ambient colour.** V23 found
  that a dark sky supplies no ambient - it raised `ambient_energy` fourfold and
  measured no change at all, because ambient is sampled from the sky and a
  near-black sky samples near-black. A room needs the opposite of a valley
  here, and this pairing is the single most important line in the base profile.
* **fog density 0.0011 against V26's 0.0038, aerial perspective 0.22 against
  0.94.** A hundred and twenty units of room is not a valley. At V26's numbers
  the far wall washed to the sky colour, which in here is near black, and the
  enclosure disappeared exactly where it was meant to be working.

---

## 11  Overhead architecture: tested, and the answer is no

Part H asks whether partial overhead structure improves containment. Three
placements were built and rendered and all three failed, for two reasons that
between them close the question for this camera track.

**Over the machine: invisible.** §4. The top of every frame is below horizontal,
so nothing above a camera's own eye height is ever in shot, at any radius.

**Over the low course: a bar across the action.** Where the track has descended
far enough for an overhead member to be in frame, the headroom between the
course and the top of the frame is 2.6 units at the finish and 4.4 at the
merge. The second attempt sat at +9 over the finish run and the winner frame
came back with a black bar diagonally across it and the FINISH board behind the
bar.

That second failure also found a real bug, which is recorded in
`environment_stage.gd` beside the fix: **the canopy builder had no camera-path
test.** Every other builder in that file and in `environment_world.gd` has one;
this one did not, because a thing that is *over* the course does not sound like
a thing that can be *in front of* a camera. The keep-out it now carries is
deliberately too strict - it is a plan test that ignores how high a member is,
because the profile's keep-out is a decimated list of plan positions with no
heights in it.

The builder stays. It is part of the stage, a course photographed from lower
cameras will want it, and concept C carries the one placement on this course
that does read (§7).

---

## 11.1  The mixer

Part L asks that the mixer read as a machine demonstration inside the chamber:
the circular mechanism framed, the meridian rotation uncontested, the violet
machine accents readable.

                          V26      A      B      C
    environment cover    0.68   0.73   0.73   0.73
    near structure      37.2%   7.6%   9.3%  11.7%
    enclosure wall      13.6%  18.2%  16.3%  14.0%
    machine - bg luma     105    100     99    103

This is the clearest sectional win in the film after the branch. V26 puts
thirty-seven per cent of the mixer frame into faceted blue rock in the upper
left, immediately behind and above the rotor; the contained stages replace that
with a wall plane and one or two column silhouettes, at a quarter of the near
count, with the machine's separation from it unchanged to within five luma.

The rotor's own violet reads against a neutral graphite wall rather than
against a saturated blue hillside, which is the reason to do it: the machine
palette is V23B's and a world that argues with it costs a colour decision that
was already made and measured.

---

## 12  The obstacle

The brief's Part M hopes a contained environment can give the obstacle the
local identity it lacks. **It can, but not with a bay.** The site search (§4.1)
found no position within 40 units of the obstacle node that is legal, in frame
and behind the action at once: the obstacle cut runs along the course and the
course is the whole frame for the first sixty units.

What the obstacle camera *does* see at distance is the region at radius 62 to
75 on bearings 20 to 55, in a value band from about −40 to 0. Concept A's lower
wall stands at radius 92 with its cornice at +4 - three units under the
measured ceiling there - and its 24-entry rhythm is written out in full so that
its indices 1, 2 and 3, at bearings 22.5, 37.5 and 52.5, are a run of three
recessed bays with warm strips in them.

So the obstacle's identity is a **pocket in the near wall**, not an object
beside the track. Measured effect: the obstacle frame's environment cover rises
from 47% to 55%, its background value spread from 24 to 46, and the wall band
occupies 8.1% of it where V26's far band occupied 2.0%.

The honest reading is that this is an improvement and a small one. The obstacle
is the section where the machine fills the most frame, and no environment pass
can give a place identity in a shot that barely shows the place.

---

## 13  The fork

The fork keeps the route colours as the primary signal - they are the
machine's, and this pass does not touch the machine. What the architecture adds
is a second statement of the same thing: a **portal with splayed wings** at the
site the search found, offset [+36, +6] from the split node on bearing 80, 58
units tall out of ground that has fallen to −24.

Two panels diverging at 34 degrees either side of a gateway, behind the point
where the routes separate. It states the split before the marbles reach it and
it is behind them when they take it.

Measured: the fork-approach and split frames carry 11.8% and 11.0% structure
band in concept A against 0% before the near columns were added, and the split
frame's parallax orders correctly in all three concepts.

---

## 14  The finish

The finish is where a contained environment should win most, and it is where
the measurements are most mixed.

**What works.** The finish gets a dedicated bay: a landing pad under the line
(authored with both placement guards switched off, which is the one form in the
stage that must not be rejection-sampled), a 40-wide frame 84 units tall rising
out of the pit behind it at bearing 58, and a warm strip near its head. The
background behind FINISH becomes a controlled dark plane instead of conifers
and rock, and the wall band's share of the winner frame rises from 1.8% to
17.5%.

**What does not.** The machine-to-background separation at the finish falls
hard:

                          V26     A      B      C
    winner crossing        90     49     48     24
    payoff                 84     53     52     33

The finish zone's own practical - energy 4.2, range 40, and V24's, not this
pass's - now lands on a wall and a deck instead of on dark rock, so the
surround is lit where it used to be black. That is a *deliberate* consequence
of giving the finish a place, and at A's and B's numbers it is acceptable: 49
luma of separation is still a machine that reads. At C's 24 it is not, and that
is most of why C is not the recommendation.

**The finish bay had to be built downwards.** The winner camera looks down at
48 degrees from 20 units, and its top of frame at 30 units past the line is
+7.2 and at 60 units is −10. Everything behind the finish that a viewer sees is
*below* the line, seen from above. A proscenium over the board would have been
out of frame; what reads is a wall rising out of the pit.

---

## 15  Phone review

`docs/validation/sloped_race_v1/v27_contained/phone.png` is the four worlds at
270×480 at the four moments that decide. At that size:

* **Frame 0** — the contained backgrounds are quieter and marginally darker;
  the racer row is the only saturated thing in the frame in all three, and is
  not in V26, where the teal terrain competes.
* **Obstacle** — V26 shows rock at the lower left; all three contained stages
  show a smooth dark floor. The clearest cleanliness win of the four.
* **Branch** — the largest difference in the film. V26's frame is busy teal
  rock edge to edge; the contained frames are a dark wall with two or three
  architectural masses in it. The marbles on the two routes are the only
  high-chroma objects.
* **Winner** — V26 has conifers and rock behind the board; A and B have a clean
  dark plane with visible wall planes; C has the strongest warm pooling and the
  darkest surround.

At phone scale A and B are hard to separate. C is obviously darker.

---

## 16  Metrics

Full tables in `docs/validation/sloped_race_v1/v27_contained/`:
`measures.txt`, `parallax.txt`, `envelope.txt`, `sites.txt`, and the JSON each
was printed from.

                                        V26        A        B        C
    racers legible / moment            4.83     4.83     4.83     4.67
    least racer dE, frame 0            65.9     71.7     71.7     71.7
    machine - background luma           109     93.1     91.6     82.2
    mean luma                          68.6     68.3     69.9     60.3
    clipped white %                    1.04     1.05     1.05     0.94
    clipped black %                    2.91     3.23     2.61     4.58
    environment cover                  0.69     0.74     0.74     0.72
    background edge px, fine %         4.56     5.55     4.78     4.43
    background edge px, coarse %      16.28    21.30    20.88    16.98
    detail surviving a squint          3.70     3.90     4.46     3.94
    background value spread            24.1     45.7     45.3     40.8
    parallax: moves ordered           0 / 5    5 / 5    4 / 5    5 / 5
    band cover: near structure        36.9%     5.2%     2.9%     8.2%
    band cover: enclosure wall         7.5%    20.0%    21.7%    21.6%
    mesh instances                     2284     1513     1319     1324
    triangles                       650,556  540,440  498,800  498,212
    ms / frame                          330      352      356      353

The band distribution, which is the argument in §18 in one table. Mean cover
over the twelve moments, and in brackets the number of moments where the band
is under half a per cent of the frame:

                          V26          A          B          C
    near ground      9.4 (0)   43.8 (0)   43.1 (0)   41.6 (0)
    near structure  36.9 (0)    5.2 (1)    2.9 (6)    8.2 (1)
    deck band       14.7 (1)    5.0 (5)    6.4 (5)    0.0 (12)
    enclosure wall   7.5 (0)   20.0 (0)   21.7 (0)   21.6 (0)

**On background complexity.** The metric is deliberately two-scale, because a
mean gradient cannot tell a wall with three hard lines on it from a hillside
covered in small ones - they integrate to the same number, and the first
version of this measured exactly that and made the contained stages look busier
than the rock they replaced. `fine` is the fraction of background pixels that
are an edge at delivery scale; `coarse` is the same after an eight-pixel blur;
the ratio is how much of the detail is *form* rather than texture. The
contained stages carry about the same fine texture as V26 and 25 to 30 per cent
more structural form, which is the shape of detail Part G asks for.

None of these is a score for good design. A blank wall measures best on every
one of them, and is the thing the brief rules out in its first paragraph.

**On black clipping, which was a real defect.** The first build of all three
concepts crushed 10 to 17 per cent of every frame to luma 5 or under, against
V26's 2.9, and 89 per cent of that black was the *wall*, not the sky. A chamber
wall faces inward, one directional key cannot reach more than half a ring of
them, and a flat panel with nothing but ambient on it renders as one near-black
value. The remedy is V25.2's, for the same diagnosis it wrote it for:
`soft_light`, a backlight term proportional to 1 − N·L that lands exactly on
the faces turned away from the key, plus `floor_lift`, a small constant
emission that is a lifted black point rather than a glow. A sixth light would
have raised the whole room and given the faces pointing at *it* a second key.
The numbers above are after that fix; the payoff frame went from 33.4% black to
5.2%.

---

## 16.1  The decision table

The brief's Part Y, scored out of five, with the control scored on the same
rows - a recommendation that is not scored against what ships is a
recommendation against nothing. Seven rows are anchored to a number this lab
measured and `tools/sloped_v27_contained.SCORES` names the anchor beside each;
the other five are taste, and saying so is more useful than dressing them up.

```
criterion                                             v26  a   b   c 
----------------------------------------------------  ---  --  --  --
do the eight marbles stay the first thing read        3    5   5   4 
does the machine stay the second                      5    4   4   3 
frame 0: racers, PICK A COLOR, START, no tangency     4    4   4   4 
foreground, midground and background all present      4    5   3   4 
three separable speeds during a camera move           2    5   4   5 
does it look expensive                                3    5   4   4 
is the background quiet behind the track              2    4   5   4 
would it host a different course                      1    5   4   3 
would it host country flags and other racer palettes  2    5   4   4 
would it host a different machine footprint           1    5   4   3 
is the payoff a place                                 3    4   4   2 
meshes, triangles and milliseconds against V26        3    4   5   5 
TOTAL (60)                                            33   55  50  45
```

---

## 17  Performance

All three contained stages are **cheaper in geometry and slightly dearer in
time**:

    mesh instances     -34% (A)   -42% (B)   -42% (C)
    triangles          -17% (A)   -23% (B)   -23% (C)
    ms / frame          +7% (A)    +8% (B)    +7% (C)

The geometry saving is real and structural: a wall is 32 boxes where a valley
is 13 walls, 26 ridges, 33 scarps, 22 spires, 42 boulders and 117 trees.

The time is not saved, and the reason is worth stating: these frames are
shading-bound rather than geometry-bound. A contained stage replaces many small
distant objects with a few very large near ones, so screen coverage goes *up*
even as instance count goes down, and SSAO, SSR and the five-light world rig
all cost per covered pixel. Seven per cent on a 330 ms frame is 23 ms, which is
twenty-eight seconds on a 1207-frame render.

There is a saving available and it is not taken: bearings 225 to 285 are never
photographed (§4), and walling only the seen arc would remove about a third of
each shell. A stage that can only host one camera track is not a stage, so all
three build the full ring.

---

## 18  Recommendation: **A — Premium machine hall**

    --environment=contained_hall

**Why it wins.**

1. **It is the only concept with four depth bands present in nearly every
   frame.** Landform 43.8%, near structure 5.2%, deck 5.0%, wall 20.0%, with
   the structure band under half a per cent in one moment out of twelve. B's
   structure band is absent in six of twelve, which makes it a two-layer
   picture at the obstacle, the final approach, the winner and the payoff. C
   has no deck band at all - its own near walls hide it.
2. **It orders all five camera moves near-to-far.** B orders four; the control
   orders none.
3. **It keeps the machine furthest above its background of the three** (93.1
   luma against 91.6 and 82.2), which is the brief's hierarchy stated as a
   number.
4. **Its material family is the most neutral** - graphite, one light trim
   value, two dim lit strips - which is the reusability requirement, and its
   rhythm (rib, bay, slot on an eight-step metre) is a language a different
   course can be given at different counts without being redesigned.
5. It is also what the brief predicted, and the evidence agrees rather than
   being arranged to.

**B is a close second** and beats A on three rows: black clipping (2.61%, which
is better than the control), the squint ratio (4.46 against 3.90 - the most
low-frequency detail of any world here) and triangles. If the channel wants the
collector-set identity, B is not a compromise; its one real weakness is the
thin near band, and that is a count problem rather than a design problem.

**C is rejected on measurement, not taste.** At the winner and the payoff the
machine stands only 24 and 33 luma above its background against V26's 90 and
84; its mean luma of 60.3 costs it a racer at every moment (4.67 legible
against 4.83); and it clips 4.58% of every frame to black against A's 3.23. It
is the most dramatic of the three and the least safe.

---

## 19  Weaknesses

Known, measured, and open.

1. **The finish separation.** A's machine-to-background at the winner is 49
   luma against V26's 90. The cause is V24's own finish practical now landing
   on a wall. A tune - dropping the finish bay's albedo a value or narrowing
   the lamp's range - is the obvious next move and it was not made here,
   because the lamp is V24's and this pass is an environment pass.
2. **Frame 0 barely changes.** The hill fills the upper left of the hook and no
   enclosure can reach it. What a contained stage buys there is a quieter strip
   along the top right and a nine per cent gain in racer ΔE. Real, small.
3. **The near band is thin by V26's standards** - 5.2% against 36.9%. That is
   the intent, but it is close to the floor: at the obstacle and the payoff it
   drops under 1%, and those two frames are wall-and-landform only.
4. **Render time is up 7 to 8%.** Shading-bound, not geometry-bound (§17).
5. **The parallax instrument is weak on this project's look.** The block
   matcher cannot track flat-shaded surfaces in either world; the overlap
   measure that replaced it is occlusion-confounded and needed a two-per-cent
   cover floor before it stopped reporting 0.99 on slivers. Both are honest and
   neither is as good as a depth-buffer measurement would be.
6. **The deck band is invisible in C** and thin in A and B outside the branch
   and final-approach shots. The floor is doing less work than the brief's Part
   I hopes.
7. **Untested with country skins.** The claim that a neutral stage hosts any
   racer palette is argued from the palette values, not demonstrated. A render
   under a flag texture would settle it and is one flag away.

---

## 20  Production integration plan

If A is accepted, the integration is small and is deliberately shaped to be:

1. **One string.** `sloped/v27.py` would be `sloped/v26.py` with
   `ENVIRONMENT = "contained_hall"`, exactly as V26 is V24 with a different
   world string. Nothing else in the repository needs to know.
2. **One edition row** in `tools/sloped_v22.py::EDITIONS`, borrowing V24's
   solved track the way V26 does, so the camera schedule stays identical by
   construction rather than by test.
3. **Close weakness 1 first** - the finish separation - because it is the one
   number that is worse than the control in a shot the film is built around.
4. **Then re-run `tools/sloped_v27_contained.py --stage all`** against the
   integrated edition, which needs no change: it renders whatever
   `--environment=` names.

Nothing about the physics, the replay, the camera solve, the edit, the machine
palette, the racer surface, the overlays or the soundtrack is touched by any of
that, and `tests/test_sloped_v27_contained.py` is the assertion that it stays
that way.

---

## Files

    sloped/v27_contained.py                      the lab's tables and measures
    tools/sloped_v27_profiles.py                 writes the eight profiles
    tools/sloped_v27_contained.py                renders, measures, reports
    godot/.../environment/environment_stage.gd   the five new builders
    godot/.../environment/environment_world.gd   +5 keys in BUILD_ORDER
    godot/.../lab_palette.gd                     +11 material keys
    godot/.../environment/profiles/              contained_base, contained_hall,
                                                 diorama_chamber,
                                                 industrial_chamber,
                                                 _marker_v27a/b/c,
                                                 _marker_v27_control
    tests/test_sloped_v27_contained.py           85 assertions
    docs/validation/sloped_race_v1/v27_contained/  contact.png, phone.png,
                                                 opening.png, middle.png,
                                                 finish.png, hook_card.png,
                                                 envelope.txt, sites.txt,
                                                 measures.txt, parallax.txt,
                                                 scores.txt
    exports/v27_contained_environment/             the boards and the clips
