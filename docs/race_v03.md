# Race V0.3 — production visuals

Answers one question: **can the same race, with the same physics and the same
outcome, be made to look like something worth stopping a scroll for?**

Nothing about the simulation changed. Not a constant, not a course, not a
seed. `git diff` touches no file under `race/`, and the twenty stored V0.1
validation seeds still reproduce bit for bit. What changed is the lens, the
lighting, the materials and the overlay — everything downstream of the replay
and nothing upstream of it.

The V0.2 render was a correct diagram: a straight-down orthographic camera, flat
slabs, coloured discs. It was built that way on purpose, because a camera that
maps one simulation pixel to one frame pixel is the only camera a render can be
mechanically checked against. That camera has not been removed. It has been
demoted to an instrument, and a second one now does the looking.

---

## How to run

```bash
# the production camera is the default for a race
python tools/render_replay.py output/race_v03/prototype_839271.json \
    --output output/race_v03/render_production_prototype_839271

# the measuring lens, when the render has to be checked against the replay
python tools/render_replay.py REPLAY.json --output DIR --race-camera verification
python tools/verify_race_render.py DIR --frames 24

# the same five moments out of any two renders, for comparison
python tools/race_moments.py DIR --out docs/validation/race_v03/after --label after
```

---

## Part 1 — two cameras

```
verification    orthographic, straight down, 1 sim pixel = 1 frame pixel
production      perspective, elevated, looking down the course
```

The mode is chosen with `--race-camera`, recorded in the render sidecar as
`video.camera`, and enforced: `verify_race_render.py` refuses to measure a
production render rather than reporting every racer as hundreds of pixels out
of place. A battle replay has one camera and always has; asking for a race
camera on one is an error.

### Why the production camera looks the way it does

**Elevation 74°, FOV 40°.** A race course is six times longer than it is wide,
and a 9:16 frame only gets its height back by looking down the length of it —
the same argument the duel's camera sits at 78° over a square arena. Shallower
and most of the frame is spent on course the racers have already left.

**The distance is derived, not dialled in.** The failure to avoid is the course
running out of frame sideways. Under a tilted lens the *nearest* visible ground
point is where the frustum is narrowest against the ground, so fitting the
course across there fits it everywhere:

```
span      = 2 D tan(fov/2) / sin(e)          ground covered, along the course
near      = D − (span/2) cos(e)
          = D (1 − tan(fov/2) / tan(e))      view distance to the near edge
half_wide = near · tan(h)                    half the frame's width there
```

Setting `half_wide` to half the course plus a margin and solving for `D` gives
the framing. On a 1080-wide course that is about 30 units back, showing roughly
2 300 course pixels against the verification camera's 1 920.

**Ahead is up-screen.** This is the one deliberate reversal from V0.2. A camera
that is tilted at all has a screen-up direction of `(0, d, h)` — it points
*down* the course — so as soon as the lens tilts far enough to show what is
coming, what is coming is at the top. The alternative is a camera placed ahead
of the racers looking back, which cannot see the upcoming course at all. At 74°
the ground is near enough to top-down that gravity reads as "into the screen"
rather than as anything falling upward, and obstacles now rise into frame and
sweep down past the camera, which is what a racing shot does.

### Camera motion

Three things move the lens, and all three are pure functions of the playhead:

| motion | driven by | range |
|---|---|---|
| follow | `camera_y`, the track the replay records | the whole course |
| dolly | field spread, averaged over the last 36 frames | ±16% of the base distance |
| push-in | seconds since the `winner` event, eased out | 10% closer over 2.4 s |
| shake | `collision` and `winner` events | ≤ 0.055 units, 0.16 s |

The dolly is averaged over *replay frames* rather than eased across draws. That
distinction is the whole reason it is allowed to exist: an accumulator would
make the framing depend on how many times the scene had been presented, and two
renders of one replay would stop matching.

---

## Part 2 — materials

`godot/scripts/race_materials.gd`. One palette, built once, shared by every
piece. Two rules decide all of it.

**The racers own the colour.** Ten saturated hues have to stay the most
colourful things on screen, so the course is built almost entirely from one
dark blue-grey metal and one cyan accent. Only the pieces a viewer must
identify instantly get a hue of their own.

**Behaviour is legible from appearance.** The simulation gives every surface
one of three materials and they behave very differently, so the physical
material picks the *finish* and the role picks the *hue*:

| surface | metallic | roughness | reads as |
|---|---|---|---|
| `TRACK` | 0.35 | 0.44 | brushed metal — grips |
| `SLICK` | 0.70 | 0.16 | near-mirror — a highlight slides along it |
| `BOUNCY` | 0.15 | 0.55 + faint emission | soft and sprung |

| role | treatment |
|---|---|
| wall | dark metal, 1.35 units tall, lit inner edge |
| peg | pale cyan emissive post |
| jump pad | green emissive plate, own material so it can flare alone |
| gate | red emissive, removed when the replay says `gates_open` |
| spinner | dark metal body, amber lit collar and arm tips |
| finish | gold, the brightest static thing on the course |

### The one change that mattered most

The first version of this scene rendered almost black. Not under-lit — *black*,
with a specular streak on each ramp. The cause is that a metallic surface is
mostly a mirror: its albedo barely matters and what it shows is whatever the
environment gives it to reflect, and the environment gave it a flat dark
colour. No amount of lifting the albedo fixes that, because the albedo is not
what is missing.

So there is a sky. It is kept out of the background — the void behind the
course is still flat and dark — and used only as a light and reflection probe.
That single change is most of the difference between the two screenshots at the
bottom of this document.

---

## Part 3 — racers

A glossy, lightly metallic sphere with `rim_enabled`, low emission (0.30 — high
enough that the hue survives a dark course, far too low to wash the shading
out), a **meridian band** and a **number**.

**The band** is a torus lying in the plane the sphere spins through. Without it
a spinning sphere and a still one are the same picture, and the replay carries a
real rotation — a measured median of 2.2–3.8° per frame — that would otherwise
be thrown away.

**The number** is a `Label3D` above the racer, in the racer's own colour with a
heavy black outline, billboarded so it always faces the camera. Above rather
than painted on: a number wrapped round a rolling sphere spends most of its time
on the far side, and the moment a viewer wants to read it is the moment a racer
is in a pile-up. An earlier version put the text at the centre of a small disc;
the disc won the depth test and the numbers were never seen at all.

**Squash** is applied to the racer's pivot as a basis, never as a position. The
axis runs from where the collision was recorded to where the racer is now, so
the ball flattens against the thing that hit it and keeps doing so as it is
pushed away. Volume is held roughly constant so it reads as compression rather
than as shrinking. Below a tenth of full strength there is no visible
deformation at all.

---

## Part 4 — trails

`godot/scripts/race_trails.gd`. One `ImmediateMesh` ribbon per racer, about
forty vertices, rebuilt from scratch every frame.

There is no particle system and there could not be. A particle system
integrates: it emits on a timer, ages particles against a delta and seeds them
from a random stream. The offline renderer never passes a delta and draws each
frame exactly once at an exact replay instant, so a particle trail would look
different on every render — and it would be *guessing* where the racer had
been. The replay already knows: frames `N−18` to `N` hold eighteen positions
the racer actually occupied.

**Speed mapping**, from measured races rather than taste. The cap is 750 px/s
and the median racing sample sits near 400, so a trail starting at zero would
be on almost all the time and would stop meaning anything:

```
speed < 330        no trail at all           (about half of all samples)
330 → 700          length and alpha ramp
> 700              full length               (roughly the top fifth)
```

A jump pad's kick adds up to 45% length and 50% alpha for 0.55 s on top of
that, so a launch reads as a launch. The ribbon breaks rather than stretches if
the racer's recovery count changes between two frames — a recovered racer has
been teleported, and joining the two sides of that jump would draw a stripe
across the course.

---

## Part 5 — event VFX

`godot/scripts/race_vfx.gd`, the race counterpart of `combat_vfx.gd`, keeping
both of that file's rules: nothing is inferred, and everything ages in replay
time. Effects appear at the coordinates the *event* carries, not at wherever
the racers involved have since got to.

| event | effect | scaled by |
|---|---|---|
| `collision` | ring + hot spark, squash on **both** racers, camera shake above 0.45 | closing speed, 620 → 980 |
| `jump` | pad flares, ring, spark, trail boost on the racer | not scaled — every jump is ~300 |
| `finish` | small ring in the racer's colour | — |
| `winner` | large ring, spark, camera shake | — |
| `retired` | ring where the racer left | — |
| `recovery` | smaller ring | — |
| `checkpoint` | **nothing** | — |

Two of those rows are decisions rather than defaults.

**The impact scale starts at 620, not zero.** The simulation refuses to record
a collision below `LARGE_COLLISION_SPEED = 620`, so scaling from zero would
compress every collision that exists into the top third of the range and make
them all look identical. Measured over three races: median 730, p90 790, max
1251. Most collisions therefore read as small, which is the point.

**Checkpoints get no world effect.** They are 60–75% of the whole event stream
— 90 to 102 per race, and on the split course all ten racers cross the start
plane on the same tick. Ten rings on one frame would look like a bug.

The jump pad that fires is the one that lights up, keyed on the piece id the
event carries in `detail`. Pads get their own material instance for exactly
this reason; every other piece shares one.

---

## Part 6 — the course reads itself

Two pieces of course architecture are derived from exported data rather than
written per course, so a course this renderer has never seen gets both for
free.

**Checkpoint bars.** A thin lit line across the track at every progress plane,
drawn across the corridor a branch plane actually exists in — so on the split
course the two paths are marked separately, at their own widths, and a viewer
can see the fork is a fork. Section portals stand where each named stretch of
course begins.

**Pinch gates.** The funnel throat is the moment the prototype is built around
and it looked like any other stretch of track. Marking it by name would put
course-specific knowledge in a generic renderer, and marking it at the nearest
checkpoint does not work either — the throat sits eighty pixels above
`funnel_exit`.

So the course is measured instead of asked. Sampling the clear width every 40
pixels finds each stretch where the track closes to under 18% of its width, and
a lit gate goes at the narrowest point of each. Pegs are excluded, because a
racer goes between them and counting them would call every row of plinko a
throat. What that finds:

| course | gates | where |
|---|---|---|
| prototype | 3 | funnel throat (140 px clear), scatter exit (157 px), jump basin (134 px) |
| split | 6 | every drop gap down the two branch corridors (102–148 px) |

Nothing in the renderer knows what a funnel is.

---

## Part 7 — environment and lighting

A dark room the course runs through: a floor slab under the track, two long
side walls just outside it with a lit strip along each, a rank of structural
ribs as one `MultiMeshInstance3D`, and a deep floor far below so the gap either
side reads as a drop into a building rather than as the edge of the world. The
ribs are what make the camera's forward motion legible — a rank of regular
objects sweeping past reads as speed in a way a smooth wall never does.

Lighting is a key, a fill and a cold kicker. The key is angled **across** the
course rather than down it: a light straight overhead puts every shadow
underneath the thing casting it, which is precisely what the V0.2 render looked
like. The kicker sits low and almost along the camera axis purely to put a
bright edge on the far side of every sphere, which is what stops ten dark balls
merging into one shape in a pile-up.

Everything expensive is off — no SDFGI, no SSIL, no screen-space reflections,
no volumetric fog. What is left is a flat ambient from the sky probe, depth fog
(the cheapest depth cue there is), SSAO at a short radius to seat a racer on a
ramp, and glow on a short leash: `glow_hdr_threshold = 1.05` sits above every
ordinary lit surface, so only pads, spinner tips, the finish and impacts bloom.

---

## Part 8 — the HUD

The V0.2 overlay lost badly to a measurement nobody had taken. YouTube draws
its own chrome over a Short — Google publishes the reserved regions as
percentages: top 10%, bottom 25%, right 10%, which on 1080×1920 is 192 px,
480 px and 108 px. Widening the action rail to 156 px for safety leaves:

```
SAFE = x 48..924, y 192..1440
```

Audited against that, three of four V0.2 elements failed:

| element | V0.2 | verdict |
|---|---|---|
| clock | y 24..100 | **entirely** inside the top chrome band |
| standings row 1 | y 116..170 | entirely hidden — the race *leader* was the one competitor a viewer could not see |
| winner panel | y 1560..1750 | under the channel/title row — the payoff frame of the whole Short was the frame the platform covered |
| countdown | y 700..1020 | passed |

V0.3 puts everything inside the safe rectangle, drops panel opacity from 0.80
to 0.52 (an 80%-opaque near-black over a near-black course reads as a hole cut
in the frame), and shrinks the block:

| | V0.2 | V0.3 |
|---|---|---|
| clock | 230×76 at (425, 24) | 220×68 at (48, 200) |
| standings | 380×178 at (42, 116) | 300×184 at (48, 284) |
| **course covered** | **85 120 px²** | **70 160 px²** (−17.6%) |
| standings font | 36 (≈13 dp — below the legibility floor) | 44 (≈16 dp) |
| result | 856×190 at (112, 1560) | 792×268 at (90, 1148), centred on 486 |

A 1080-wide frame is watched at roughly 400 logical pixels, so source pixels
divide by about 2.7. Sixteen device-independent pixels is the usual comfortable
floor for text; every label is now at or above it. Outline size is scaled with
font size (`clamp(font/9, 4, 18)`) instead of a flat 6 — at font 36 a flat 6 is
17% of the em and closes the counters of `a`, `e` and `o` after re-encode; at
font 300 it may as well not be there.

`tools/verify_race_render.py` carries the same rectangles so it can skip racers
hidden behind the overlay, and `tests/test_race_visuals.py` parses the GDScript
and fails if the two ever drift apart.

---

## Part 9 — determinism

The single biggest risk in a visual phase, and the reason several obvious
techniques are absent. The offline renderer seeks to `frame / fps` and draws;
it never passes a delta. Anything that integrates, accumulates or randomises
would produce a different picture at a different render speed.

Banned, and asserted as banned by a test that scans every race script with
comments stripped:

```
GPUParticles3D  CPUParticles3D  Tween  AnimationPlayer  randf  randi
Time.get_ticks  use_taa  sdfgi_enabled  auto_exposure  volumetric_fog_enabled
```

Also avoided: `Sky.PROCESS_MODE_REALTIME` (reuses previous-frame radiance —
`PROCESS_MODE_QUALITY` recomputes), and any shader reading `TIME`.

Angles are interpolated with `lerp_angle` throughout. Rotation wraps through
the 0/360 seam on about 1.4% of frame steps, and a naive lerp would spin a
racer a full turn backwards on those frames — deterministic, so the byte
comparison would never catch it, and visibly wrong.

---

## Test results

Full suite: **1010 passed** (977 before this phase). New:
`tests/test_race_visuals.py` (33).

What the new tests actually check, since none of them render a pixel:

* **camera modes** — the race defaults to production, verification stays
  reachable, both plan the identical sequence, a battle cannot be given a race
  camera, and `verify_race_render` refuses a production render *before* the
  `--replay` override rather than after it.
* **the simulation stays authoritative** — no forbidden API in any race script,
  no `_process`, spinner transforms read rather than integrated, squash writes
  a basis and never a position, effects placed from event coordinates, events
  with a null position skipped, the impact floor equal to
  `LARGE_COLLISION_SPEED`, the trail threshold inside the measured speed range,
  and no visual vocabulary anywhere under `race/`.
* **the platform contract** — every overlay rect inside the safe rectangle,
  every font at or above the legibility floor, the HUD and its verifier in
  agreement, and the overlay measurably smaller than V0.2's.

Image tests for lighting are deliberately absent: a tenth of a degree on a key
light changes every byte and tells you nothing about whether the change was
good.

---

## Validation

### Determinism

The claim the whole architecture rests on. Two full production renders of
`prototype_839271`, 1 707 frames each, 39 sampled:

```
byte-identical  39/39      IDENTICAL
```

### Replay alignment — the verification camera

`prototype_839271`, verification camera, 24 frames sampled:

```
171 racer positions measured, 25 behind the HUD
located 171, missing 0
position error: mean 1.17px, median 0.78px, 95th 4.03px, worst 14.61px
silhouette vs replay diameter: mean 1.03x, range 0.98-1.55x
```

Better than V0.2's 1.50 px mean on the same replay, because a flat unshaded
racer is easier to find than a lit one. Asking the tool to check a *production*
render is refused rather than answered.

### Before and after

Rendered from the same replay files, at the same frame indices, so the only
difference between a pair is the renderer. `docs/validation/race_v03/`:

| moment | frame | before | after |
|---|---|---|---|
| start | 0 | `before/v02_839271_start.png` | `after/v03_839271_start.png` |
| spinners | 337 | `before/v02_839271_spinners.png` | `after/v03_839271_spinners.png` |
| funnel | 554 | `before/v02_839271_funnel.png` | `after/v03_839271_funnel.png` |
| jump | 784 | `before/v02_839271_jump.png` | `after/v03_839271_jump.png` |
| finish | 1207 | `before/v02_839271_finish_line.png` | `after/v03_839271_finish_line.png` |

Also `v02_1015_*` / `v03_1015_*` (four moments, the impacts-and-jumps seed) and
`v02_split1000_*` / `v03_split1000_*` (five moments, the branching course).

The `before` set for seeds 839271 and 1000 is the V0.2 render as it shipped.
The set for 1015 was produced by checking out commit `0696ea1` into a git
worktree and rendering there, because that seed had no V0.2 render to compare
against.

### The Short

```
output/race_v03/render_production_prototype_839271/short.mp4
  h264 High  1080x1920  yuv420p  60/1 CFR  1707 frames  28.450s  22.2 MiB
  no audio track (races encode silent; there is no race soundtrack yet)
```

---

## Performance

RTX 3050 Laptop, 1080x1920, offline render including the frame readback and the
PNG write:

| render | fps | ms/frame | frames | wall clock | PNG |
|---|---|---|---|---|---|
| production, prototype 839271 | 6.7 | 148 | 1707 | 252.9 s | 918 MiB (551 KiB/frame) |
| production, prototype 1015 | 6.3 | 159 | 1662 | 263.7 s | 911 MiB |
| production, split 1000 | 6.2 | 162 | 1245 | 201.9 s | 682 MiB |
| verification, prototype 839271 | 8.4 | 119 | 1707 | 203.4 s | 797 MiB |
| *V0.2 reference (split 1000)* | *10.2* | *98* | *1245* | *122.6 s* | *383 MiB* |

Encoding is not the bottleneck: 1 707 frames to MP4 in 25.6 s (67 fps).

Interactive preview, 540x960 window: **143-145 FPS**, which is the display's
144 Hz refresh — the preview is not GPU-limited, so the headroom the next phase
needs is there.

The production render is about 35% slower per frame than V0.2's flat one. That
buys shadows, SSAO, glow, depth fog, an environment probe and roughly three
times the geometry. A 28-second race takes 4.2 minutes.

Where the cost is *not*: nothing here is volumetric, there is no SDFGI, no
screen-space reflection and no post-process beyond glow. A meaningful share of
the 148 ms is the `get_texture().get_image()` readback and the half-megabyte
PNG write per frame, which V0.2 paid too.

---

## Compatibility

**Fight mode is byte-identical.** `output/batch_audit10/replays/003_seed_21465.json`
- a v6 battle replay with no `mode` field - re-rendered after every change in
this phase and compared against the render made before it:

```
frames 969   compared 26   byte-identical 26/26   IDENTICAL
```

That is the strongest available statement and it is the expected one: the
battle path in `replay_viewer.gd` is untouched, and `project.godot`,
`offline_render.gd`, `combat_vfx.gd` and `battle_hud.gd` are not in the diff at
all. `--race-camera=battle` is sent for a battle replay and the race camera
parser is never reached.

**The simulation is untouched.** `git diff` includes no file under `race/`,
`replay/`, `engine/`, `modes/` or `evaluation/`. All 20 stored V0.1 race
validation seeds reproduce bit for bit, and `tests/test_race_visuals.py`
asserts that no visual vocabulary has leaked into the `race/` package.

---

## Known issues

1. **The verification camera no longer looks like the production one.** It
   renders flat unshaded racers with no band, number, trail, effect, squash or
   glow. That is deliberate - it is a measuring instrument and the presentation
   was making it unmeasurable - but it means a verification render proves
   *positions* and says nothing about materials or lighting. Those are checked
   by eye, against the before/after stills.

2. **Ahead is up-screen, which reverses V0.2.** Any camera tilted far enough to
   show upcoming course has a screen-up direction pointing down the course; the
   alternative sees nothing of what is coming. Consequence: the pygame preview
   in `race_main.py` still draws the old top-down orientation, so the developer
   preview and the production render now disagree about which way the race
   runs. The preview was not part of this phase and was left alone.

3. **Offline rendering is 35% slower**, 4.2 minutes for a 28-second race. Fine
   for one Short, a real cost for a batch of fifty.

4. **The silver racer is still the hardest thing to measure.** Its hue is the
   closest of the ten to the course chrome, and it produces the 14.6 px
   alignment outlier and the 1.55x silhouette. A distinct colour would be
   better than a wide tolerance.

5. **A race that times out has no result panel and no finish reaction.** Both
   are driven from the `winner` event, and a race with no winner has none.
   Correct behaviour, never seen rendered.

6. **The HUD depends on Godot's default font.** If the engine's built-in font
   changes between versions, every text pixel changes and archived renders stop
   reproducing. Pinning a `.ttf` would fix it and was not done.

7. **No audio.** Races encode silent. `--force-audio` will run the *battle*
   soundtrack against a race replay and produce something meaningless.

8. **A recovered racer loses its trail** for up to 18 frames. The ribbon breaks
   rather than drawing a stripe across the course, which is right, but the
   recovery itself has only a small ring to mark it.

---

## Recommendation

Do not start V0.4 from this list without deciding which direction matters. In
the order the results argue for:

1. **Audio.** It is now the largest single gap between this and something
   publishable, and it is the one remaining sense the Short does not use. The
   replay already carries everything a cue schedule needs - the battle
   soundtrack is built from exactly this shape of event stream - so the work is
   a race cue vocabulary rather than new infrastructure.

2. **Race curation.** Nothing scores a race, so there is no way to pick a good
   one out of fifty. Now that a race looks good, choosing *which* race to
   render is what stands between the pipeline and a channel. The telemetry to
   score on has been collected since V0.1 and nobody has looked at it.

3. **A pass on batch render cost.** 4.2 minutes and 918 MiB per Short is fine
   for one and awkward for a batch. Most of it is PNG. Rendering straight to a
   video stream, or to a cheaper intermediate, is a contained piece of work.

4. **The cinematic camera director**, and only then. The single follow camera
   is doing well and a director is a large piece of work whose value is hard to
   judge until there is a reason to cut - which is what a scoring system would
   provide.

Explicitly not recommended yet: procedural generation, alternate contestant
shapes, additional themes, and a third course. Each is easier once there is a
way to tell whether the result is any good.

---

## Files

**New**

```
godot/scripts/race_materials.gd   the palette and every material
godot/scripts/race_trails.gd      replay-history speed trails
godot/scripts/race_vfx.gd         event-driven impact, jump and finish effects
tools/race_moments.py             the same named moments out of any race render
tests/test_race_visuals.py
docs/race_v03.md
docs/validation/race_v03/
```

**Modified**

```
godot/scripts/race_scene.gd       two cameras, materials, environment, lighting,
                                  racers, pinch gates, pad flares, finish reaction
godot/scripts/race_hud.gd         rebuilt inside the Shorts safe area
godot/scripts/replay_viewer.gd    --race-camera parsed and passed on
rendering/render_plan.py          the camera in the plan and the sidecar
tools/render_replay.py            --race-camera, passed to Godot
tools/verify_race_render.py       refuses a production render; new HUD rects
tests/test_render_plan.py         the sidecar's video block now carries a camera
```
