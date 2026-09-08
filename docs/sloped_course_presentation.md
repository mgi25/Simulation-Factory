# Presentation polish for the sloped race course

A presentation pass over the approved sloped course, based from
`marble-sloped-course-lab` at `62edcb9`. It changes how the course is lit,
finished, supported and photographed. It changes nothing about where the course
goes.

Everything here is intended to be cherry-picked into the final race branch
*after* the physics is frozen. Nothing here should be merged into a physics
branch now.

## The invariant this branch is built on

`docs/validation/sloped_course/physics_layout.json` was dumped before the first
edit and again after the last one, and the two files are **byte-identical** —
every run, every resampled centreline, every entry and exit socket, every
solved bank angle, every module anchor and yaw, the whole terrain config, the
clearance metrics, and all nine of the cameras the sloped-course pass already
published.

That is the strongest available statement of what was not touched, and it is
checkable rather than asserted:

    python tools/course_lab.py shots     # regenerates the file
    git diff --stat docs/validation/sloped_course/physics_layout.json

The committed file is deliberately **not** regenerated on this branch, and
neither are the seven committed section stills beside it. They are the *before*
of every comparison here, and a presentation pass that overwrites its own
reference cannot be reviewed. The nine original camera entries survive
untouched because the eleven candidates this branch adds are flagged
`candidate` and published to their own file instead.

## What changed

### Environment

**The mountain was tan because of a light, not a material.** The sloped-course
pass found one cause of this and fixed a real one — the terrain was off the
world's light layer, so the warm product key hit it at full energy. There was a
second cause on the same symptom: `WorldWarm`, a 2.3-energy `#FF9C46`
directional aimed eight degrees below the horizontal, which lands on the broad
camera-facing planes of the flank and not merely on its edges. A saturated
orange at that energy across a broad plane comes back tan. At 1.5 and five
degrees it is a rim light on ridges, crag arrises and terrace lips, and the
flank goes back to rock.

The warmth that removed is returned locally, attached to things that could be
emitting it: ten small lit outposts on the wall shoulder and the gorge lip, a
warm lens on every third lamp mast, warmer valley platforms, and half the
distant slab towers rebuilt in a warm value.

**The dusk band had never been drawn.** `_dusk_band` orients its nine warm
slabs with `look_at`, which requires the node to be inside the tree, prints
"Node not inside tree" and does nothing when it is not — and `group` does not
join the scene until `build` returns. Every slab kept its default orientation
and seven of the nine were edge-on. That is most of why the dusk read as a flat
mauve wash rather than as a lit horizon. Fixed with
`look_at_from_position`, and the same mistake was caught in this branch's own
haze veils before it shipped.

**Depth fog with a floor under it.** The sloped-course pass named the real
tension and could only trade one side against the other: a density that hazes a
cliff at two hundred units also hazes the finish from a camera at the start.
`fog_depth_begin = 52` resolves it instead of trading it — nothing inside
fifty-two units is fogged, so the subject is crisp from any camera on it, and
everything past the massif's shoulder still recedes. Density then comes *down* a
fifth, because it is finally free to be set for reading distance rather than for
hiding the far edge.

**Rock with an arris.** The mountainside read as clay, and the obvious fix is
the wrong one: separating the ground materials again would undo the
sloped-course pass's own finding that a band boundary on a heightfield is a
per-quad staircase at cell resolution. So `height`, `normal` and `_material_of`
are untouched and the silhouette is bought with geometry — thirty-eight crag
clusters on the steep faces and thirteen masses on the crest line, plus
forty-four stands of foliage at a scale that survives sixty units.

Four layers of translucent haze at 190, 330, 500 and 760 replace two banks of
opaque slab. An opaque mass at four hundred units is another range, not a veil
in front of one.

### Track and materials

The blown-out white road was never the running surface. `running_polished` is a
bright albedo under a clearcoat of roughness 0.03, and a lobe that tight returns
almost all of its energy into a two-pixel band — which, with the glow threshold
at 1.16, was over the knee down the whole length of a straight. Three changes,
each addressing one term:

* the running surface gets a broader lobe and half a step less albedo
* the product key comes down from 3.2 to 2.65, because the pearl shoulder was
  clipping before the bloom ever saw it
* the glow threshold goes up to 1.48, so only the emissive stock and the chrome
  bead clear it — at 1.16 the bloom was not haloing the edge lights, it was
  washing the entire channel

The seven edge lights come down from energy 7–10 to 5.4–6.2 and are re-cut as a
journey: cyan off the line, aqua through leg 1, a neutral violet through leg 2,
full violet on the approach, blue against orange at the choice, gold to the
flag. The guard tint steps with them, which is what makes a zone read at phone
size — a 0.062 tube is two pixels there and a wall down both sides is twenty.
The practical spill lights step through the same eleven stations, so the *air*
around the track changes temperature as the race goes on.

**How much of a racer a guard is actually in front of.** Measured, because the
intuition is wrong and it constrains every camera. In profile units the guard
spans y 0.28 to 0.54 at |x| 1.03; a 0.285 racer in the cradle has its centre at
0.025 and its crown at 0.31. The guard's top arris stands **0.23 above the top
of a racer**. Clear-over-the-near-guard elevation, side-on: 18.2 degrees for the
far lane, 26.6 for the centre, 46.4 for the near. Every section camera sits
between 9 and 33 degrees, so a racer in the near half of the channel is always
seen *through* the acrylic and never over it.

That makes the guard's alpha a trade rather than a free improvement, which is
why it stops at 0.150 and why the visibility gain is bought in the rim term
instead — a cast wall is seen because its top arris catches the key. It also
gives the physics session one hard constraint: **the guard must not get
taller.** Every unit it grows is camera elevation the whole shot list has to buy
back.

### Supports

The review called the trestles loose sticks, and the previous pass had already
correctly refused to add members: a diagonal per level per face is four more
tubes in a frame that already has four legs. Both notes are right, and together
they say the missing thing is not a member — it is a **flat**. A bundle of
cylinders has no plane to catch the key, so it has no highlight and no
silhouette at any distance. Gussets, base plates, leg shoes and a head web give
the same frames flats without one new crossing line.

Two new kinds, both from the brief:

* **cantilever** — where the uphill bench stands above the keel, the bracket
  comes off the hill instead of a column rising past it, so the load path is
  visibly into the mountain. That is what an installation on a benched route
  does, and it is the one thing a column under the centreline cannot say.
* **plate girder** — between two adjacent trestles, a web under the keel, so a
  gorge crossing reads as one bridge rather than two towers with track lying
  across them. Hung under the keel and never over it: the camera rule about
  supports not crossing the action area is a rule about geometry first.

`SUPPORT_SPACING`, `KEEL_DROP` and the clearance sample loop are untouched, so
`min_clearance`, `max_clearance` and `buried_piers` reproduce exactly. Every
pier stands where it stood.

The lamp masts were the actual clutter, and the first guess about them was
wrong. The offenders were not the twelve-unit columns over the gorge — those
read as pylons. They were the *four*-unit ones on the open slope, where a 0.13
tube with a footing box on the end is a plumb line at every distance. So a mast
now stands on the ground only where the ground is within a unit and a half, and
is otherwise bracketed off the track structure. Spacing goes from 11 to 17 with
every third mast taller and warm-lensed, so the row has a beat rather than a
pitch.

### Cameras

Eleven candidates, in `docs/validation/presentation_polish/cameras.json`.
Candidates, not cuts: no timing, no selection, and no final replay to time them
against. What is settled is the shot language — where a camera stands for each
kind of section, how high, how far round from the direction of travel, and how
much is in frame.

| # | shot | style | elev | bearing | extent | progress |
|---|---|---|---|---|---|---|
| 1 | `start_event` | close 3/4 event | 20 | 30 | 17.4 | 0.00–0.03 |
| 2 | `first_descent` | low follow | 11 | 26 | 13.0 | 0.00–0.07 |
| 3 | `fast_turn` | outside tracking | 24 | 70 | 17.0 | 0.17–0.26 |
| 4 | `hairpin` | high 3/4 | 33 | 30 | 19.0 | 0.38–0.48 |
| 5 | `long_straight` | follow, off square | 11 | 22 | 16.0 | 0.30–0.42 |
| 6 | `obstacle_action` | tight action | 22 | 48 | 17.0 | 0.40–0.55 |
| 7 | `split_wide` | wide elevated, both branches | 30 | 6 | 48.0 | 0.55–0.95 |
| 8 | `final_sprint` | low forward tracking | 20 | 162 | 15.0 | 0.92–1.00 |
| 9 | `finish_push` | warm dramatic push-in | 16 | 42 | 18.0 | 0.98–1.00 |
| — | `environment` | environment plate | 9 | 118 | 62.0 | 0.16–0.85 |
| — | `track_materials` | material plate | 22 | 52 | 8.6 | 0.35–0.38 |

Every clearance claim in that file is **measured against the built scene**, not
asserted. Terrain occlusion is walked against `course_terrain.height` at
forty-eight samples per sightline; support occlusion is a capsule test against
each pier's own bounds; guard occlusion is a strip crossing in the section's
rolled frame. The result for all eleven: no empty shot, no terrain occlusion, no
support occlusion. The only flag that remains is the count of racers seen
through an acrylic wall, which is the geometric fact above and not a defect.

Three framings the brief asked for had to be argued with, and the file records
why in each case:

* **the split** was the worst failure on the course and the easiest to fix. The
  committed shot aimed at the split module with an extent of 15 while the two
  branches diverge by 36 units, so neither route was in frame. It needed a new
  primitive — an aim point at the midpoint of two runs at matching progress —
  because a split is the one race moment whose subject is not on a run.
* **the long straight** was asked for as a side follow, and a side bearing was
  tried at 66, 48 and 42. Each one put the channel across the top third of a
  portrait frame with hillside filling the rest. At 22 the run recedes down the
  frame and carries five racers strung out along it. It is still a follow; it is
  just not square.
* **the first descent** was asked for as a low follow, and on this run "behind"
  is uphill: at bearing 158 the camera stood inside the mountain. Reversed to
  26 the same low elevation reads the plunge against the sky and the field comes
  at the lens.

Two bugs were found by the verification rather than by eye, and both are worth
keeping:

**`course_scene` was holding the wrong mountain.** `Layout.table` hands out a
fresh deep copy on every call, and it is called once in `course_machine` and
once in `course_scene` — and only the machine's copy ever receives `cut_index`
from `Terrain.index_cut`. So every `Terrain.height` query from the camera rig
was answered by the *un-benched* hill, which along the whole racing line stands
up to `cut_depth` too high. Two things were reading it: the occlusion walk added
here, and the pre-existing bearing probe that decides which side of a leg is the
open one. The occlusion walk is what found it, by reporting three cameras as one
hundred per cent blocked by ground while their rendered frames were clear — a
figure too round to be geometry. `course_machine` now publishes the built config
and the scene adopts it.

**A support gauge was being looked up by a name that cannot match.**
`Track.build` is handed `name.capitalize()`, and GDScript's `capitalize` inserts
a space before a digit, so `leg1` becomes the node `Leg 1` and asking the layout
table for `"leg 1"` misses. The old lookup pushed an error and silently fell
back to `runs[0]` three times per build. Harmless so far only by coincidence —
launch and all three legs carry `HERO_SCALE` — but the moment a leg is given a
scale of its own, which is exactly what a start-fairness pass might do, the
supports under three of the four longest runs would be built at the wrong gauge.
Paired by index now.

### Phone-size review

`docs/validation/presentation_polish/phone.png` is six candidates at 390 logical
pixels with what each is checked for, plus one detail crop of the split. All six
pass: racers stay visible, direction of travel is unambiguous, blue and orange
stay separable, the finish is unmistakable, and the supports stay subordinate.

One honest gap is unchanged from the sloped-course pass, because it is not a
presentation question: in the two widest frames a marble is a three-to-five
pixel dot at phone size, so it reads as a coloured dot rather than as a glass
sphere. That is the marble's scale against a 1.88 channel and it would need a
decision about marble size, which belongs to the physics session.

## Rendering

    set GODOT_BIN=...\Godot_v4.7.2-stable_win64_console.exe
    python tools/presentation_lab.py preview     # eleven candidates, fast
    python tools/presentation_lab.py shots       # deliverables + cameras.json
    python tools/presentation_lab.py sheets      # contact, before/after, phone
    python tools/presentation_lab.py motion      # the camera proof

`tools/course_lab.py` is unedited and still renders the approved sloped-course
proofs from the same scene with the same seven lenses.

The camera proof at `output/presentation_polish/camera_proof.mp4` is eight
seconds over six of the candidates. It is **not** a race video: there is no race
in it, the marbles are a display field moving at a constant rate, and the
physics session has not frozen the start, the orange transition or the seed. Its
only purpose is to show that the cuts hold, the environment survives a move, and
the materials respond to a swinging lens. `output/` and `*.mp4` are gitignored,
so it does not travel with the branch — re-run `motion` to reproduce it.

## What this branch deliberately did not do

Every item below was in scope to *document* and out of scope to implement.

* **The start mechanism.** No geometry, no mixer art, no sockets, no bays. The
  start's camera framing changed and its sign is now uncropped; nothing it is
  looking at moved.
* **The orange local transition.** The fork mouth and the branch lead are
  untouched. Orange received its route colour language and its edge light like
  every other run, and nothing else.
* **Leg 1 and leg 2 reliability.** Not examined. No sample in `[70..99]` on
  either leg was read for anything but a camera aim point.
* **The guard's height.** The measurement above says a racer is seen through the
  near wall from every section camera, and the fix for that would be to lower
  the guard — which is collider-facing geometry. Documented only.
* **Marble scale.** The phone-size gap above wants a larger marble relative to
  the channel. That is a physics decision.
* **Fairness.** Nothing here simulates. No claim is made or implied about lane
  bias, branch parity or completion.
