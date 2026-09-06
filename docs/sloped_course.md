# The sloped race course

A long premium downhill marble course installed on a mountain flank, replacing
the vertical tower composition locked on `marble-final-visual`. That build is
kept as an **asset library** — `v2_track.gd`, `lab_palette.gd`, `lab_forms.gd`,
`toy_geometry.gd`, `v2_forms.gd` and `hero_world.smooth_mass` are all reused
here, and only `lab_palette` and `v2_track` were touched at all, both additively
— and its layout is not kept.

## What it is

| | |
|---|---|
| centreline | 236.9 units (one branch of the choice) |
| drop | 36.9 units, mean grade 8.8° |
| footprint | 38 across × 78 deep |
| start to finish | 101.1 units in a straight line |
| hero channel | 1.88 clear — three 0.57 racers abreast |
| branch channel | 1.54 clear — two abreast, the same moulding at 0.82 |
| ground clearance | 1.66 to 10.16 under the keel; **no buried pier** |

    START            8 bays abreast on a shelf under the crest
      |              the plunge - 32 to 36 degrees, the steepest thing here
    LEG 1  40.9u     long fast right-hander into a tight hairpin
    LEG 2  44.9u     the race straight, a gentle S, hairpin at the wall
    OBSTACLE         a spinner corridor on the second terrace
    LEG 3  34.1u     one long violet-lit sweep to the choice
    SPLIT            blue: the smooth inside arc, 40.6u
                     orange: out over the gorge on trestles, 41.0u, banked 32
    MERGE            two inlets, one gold-collared throat
    FINAL  21.7u     a steep pitch, then a viaduct sprint across the valley
    FINISH           a warm arena on a promontory ten units above the floor

## Phase 1: the layout study

Three structurally different courses, drawn from the same blockout builder with
the same materials and the same camera rig, so the comparison was of shape only.

| | length | drop | span x / z | start to finish |
|---|---|---|---|---|
| A cliff descent | 145.9 | 31.3 | 31.0 / 70.3 | 82.8 |
| B zig-zag raceway | 165.7 | 31.0 | 32.1 / 60.6 | 73.4 |
| C open mountain run | 143.5 | 32.0 | 34.0 / 82.4 | 90.9 |

`docs/validation/sloped_course/layout_comparison.png`

**B was selected.** It was the longest by twenty units, its four legs were the
only ones that read as *straights* rather than as one continuous snake, and its
split was the only one whose two routes could be told apart at phone size. A
and C each lost the top third of the frame to a thin ribbon; B fills the height
with four terraces, which is also four separate camera positions.

C's split was the widest and best of the three, and its idea — branches thrown
right across the terrain and pulled back — was carried into B's development.
B's own legs were then rebuilt: 165 units became 237, each leg was given a
different curve character, and the terrain was re-authored underneath it.

## The three systems this branch adds

**A queryable mountainside.** `course_terrain.gd` is a heightfield, not a
backdrop. `height(x, z, cfg)` is the single source of truth: the same function
builds the mesh, tells every support how long to be, sites every boulder and
picks every camera's open side. The flank falls at the legs' own average
descent, each terrace step falls at a hairpin, a wall rises on -X and a gorge
opens on +X, and beyond seventy units the massif fades away so the ranges and
the sky get the top of the frame.

**A bench cut from the racing line.** Wherever the hill would stand higher than
the track, the ground is cut to a fixed depth below it. That is what a real
installation does, and it means every pier has a positive length by
construction rather than by hand-tuned coordinates.

**Supports that belong to the track above them.** Each run is walked at a fixed
arc length and asked how far its keel is above the ground. Under a metre it
gets a plinth, under eight a Y-frame, over eight a braced trestle whose stock
thickens with the span it carries. Nothing hangs off anything else, which is
the structural half of "this is not a tower".

## Findings worth not rediscovering

**The ground has to be on the world's light layer.** The terrain was built in
`course_machine` and never assigned to layer 2, so the warm three-quarter
product key lit it at full energy and every face turned toward that key came
back tan. Read as a material fault it is unfixable; it is a light-mask fault.

**Material bands must be read off the macro surface — and then mostly
abandoned.** Thresholding a four-octave heightfield at a fixed height gives a
fifteen-unit fringe of interleaved patches. `height(x, z, cfg, false)` returns
the same surface with the noise off and fixes that. But the deeper problem is
that a band boundary on a heightfield is assigned *per quad*, so it is a
staircase at cell resolution: with a value jump either side it is the most
visible edge on the mountain. Three nearly-equal rock values, and form carried
by lighting and scatter instead, is what finally made the terrain read.

**A bench must be cut from the nearest centreline sample, not from a union of
one disc per sample.** A union of smoothstep discs scallops where two of them
meet at a shallow angle, and along the ridge between two switchback benches
that scalloping read as a band of sawteeth. It survived a shadow-quality pass
and a material-band pass because it was neither.

**Which way a side-on bearing swings is decided by the ground.** "The track's
left" is uphill on a leg running one way and downhill on the leg running back,
so a bearing of 78 degrees is a tracking shot on one leg and a camera buried in
the mountain on the next. The rig probes the terrain either side and takes the
open one, which is also the correct answer artistically.

**A long course's establishing lens has to be solved, not typed.** Three
layouts with the same bounding box need distances twenty per cent apart. The
rig binary-searches the smallest distance at which every centreline sample and
every module anchor is inside the frame with a margin, then recentres and
solves again.

**Signs face downhill.** Every camera on this course stands below what it looks
at, so a sign built facing uphill is a dark rectangle in every frame it appears
in.

**A start is a grid, not a funnel.** The first build opened the running channel
to two and a half times its width for four units to fan eight lanes into one;
the flare was a white shell that swallowed the pod behind it. The convergence
belongs *on the deck*, the way it does on the real sample, and an apron is a
different section from a channel — no keel, no acrylic guard.

## Fairness

**UNVERIFIED, and no claim is made.** Nothing in this branch simulates. The
eight-bay grid, the mixer's two staggered pin rows and the two branch lengths
(40.6 against 41.0) are shapes, not proofs.
`docs/validation/sloped_course/physics_layout.json` says so in the file and
carries every anchor, socket, slope, bank and clearance a PyBullet pass would
need.

## Rendering

    set GODOT_BIN=...\Godot_v4.7.2-stable_win64_console.exe
    python tools/course_lab.py study        # the three layout blockouts
    python tools/course_lab.py preview -l b # one fast frame, for iterating
    python tools/course_lab.py shots        # hero + seven sections + the JSON
    python tools/course_lab.py sheets       # the four comparison sheets
    python tools/course_lab.py motion       # the eight-second camera proof

## Honest gaps against the concept

`visual_quality_comparison.png` puts the concept's hero column beside ours at
equal height, neither cropped. Three differences are real, and none of them is
a defect of this pass:

* The concept's environment is warmer and far more densely dressed — foliage,
  lit ground, warm architecture at the base. Ours has lamp masts, ridge pylons,
  scrub and valley platforms, and is still the cooler frame.
* The concept's marbles are large relative to their track. Ours are at true
  scale against a 1.88 channel, so at phone size they read as coloured dots
  rather than as glass spheres.
* The concept stages seven modules as landmarks. Ours spends most of its length
  on open track, which is the whole point of the pivot — but it does mean four
  of the seven race moments are events on a channel rather than machines.
