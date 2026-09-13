# V22.1 — the course preview, made to breathe

Branch `v221-preview-breathing`, off the accepted V22 integration
(`57d50da`). Nothing here changes the simulation, the seed, the map, the
shuffle, PICK ONE, the chase cameras or the finish. It edits no existing file:
the whole pass is three new ones — `sloped/v221_preview.py`,
`tools/sloped_v221_preview.py` and `tests/test_sloped_v221_preview.py` — and the
V22 files it would eventually plug into are listed at the end, unchanged.

## The complaint, and what was actually wrong with it

The V22 preview is 120 frames — 2.000 s of output — and it tries to show the
finish, the final section, the merge, the branches, the fork, the obstacle, the
turns and the start in that time. Watched on a phone it reads as *there is a
course* and not as *this is the challenge*.

Measured, the reason is flat. Here is how long each landmark is the **subject**
of the shot in V22 — the frames whose gaze is on it, which is the segmentation
`sloped_race_render.gd` already cuts by:

| landmark | V22, 2.0 s |
|---|---|
| finish | 0.217 s |
| merge | 0.417 s |
| branches | **0.133 s** |
| fork | 0.217 s |
| obstacle | 0.217 s |
| turns | 0.233 s |
| mixer | 0.333 s |
| start | 0.233 s |

An eighth of a second on the split. A fifth on the obstacle. Those are under the
time it takes to find an unfamiliar object in a frame, never mind recognise it.
And the two longest windows in the shot go to the merge and the mixer, which are
not on the brief's priority list at all.

So the fault is not only that the shot is short. It is that **the shot is
uniform**, and a uniform flight over a course whose interest is not uniform
spends the same screen time on the fork and on the hillside above it.

## What the pass does

`sloped/v221_preview.py` lengthens the shot and spends the extra time unevenly.
It reuses `sloped.course_preview` entirely — the course line, the corridor, the
lift solver, the aim envelope, the landmark segmentation, the track writer,
`path_report` and `check_preview` — and changes exactly one function of it: the
map from frame number to station along the corridor, which lives on a single
line (`course_preview.py:721`). That line is substituted for the length of one
solve, so with a flat density this module reproduces V22's frames to the last
decimal. `test_a_flat_pace_reproduces_the_shipped_solver` asserts it.

### The pacing is a density, not a set of pauses

The design input is a **time density** `tau(q)` over travel `q`, where `q = 0`
opens on the finish arena and `q = 1` is behind the start machine. It is 1 over
generic track and rises into a Gaussian bump at each landmark, plus two end
terms that slow the opening and the arrival. Its normalised integral is the map
from output time to travel, and the solver wants the inverse.

A landmark's share of the shot is then very nearly `weight × sigma × 2.5066 / Z`
— a dial with an interpretable unit, not a magic number. The weights are the
brief's own priority tiers:

| tier | landmarks | dwell weight × sigma |
|---|---|---|
| high | fork, obstacle | 0.050, 0.078 |
| high | branches (the split, with fork) | 0.045 |
| high | finish, start | bought by the two end terms |
| medium | merge, turns | 0.023, 0.032 |
| low | mixer | 0.004 |

Nothing stalls. `tau` is bounded, so the flight always has speed, and the
slowest moment of the recommended candidate still travels 0.15 of its own mean —
a settle, not a pause. The brief's "not every feature needs an artificial pause"
is a property of the construction rather than a thing that was checked for.

### The trap: breathing is bought from the straights

Time in the shot is conserved. The dwell above raises the density integral `Z`
from 1 to **2.144**, which makes the flight 2.144 times faster over generic
track than a uniform flight of the same length. Station travelled per frame
where the density is flat:

| candidate | frames | straight-track rate | V22's own peak |
|---|---|---|---|
| preview_28 | 168 | **1.229** | 1.074 |
| preview_32 | 192 | **1.074** | 1.074 |
| preview_35 | 210 | **0.982** | 1.074 |

This is the single most important number in the pass, and it is the one that
decides the duration. A 2.8 s breathing preview crosses the *low-priority* parts
of the course 14 per cent faster than V22 crossed anything, anywhere — so it
buys legibility at the fork by taking it away from the run-in to the fork, which
a viewer still has to track through. 3.2 s lands exactly on V22's worst moment,
to three decimals. Only 3.5 s comes in under it, with 9 per cent to spare.

Three independent constraints — the priority weights, the recognition floors and
this bar — pin the minimum duration at 193 frames, or 3.22 s. That is why the
recommendation is the long end of the brief's range and not the middle.

### Where the shot warps, the composition warps with it

`course_preview` authors the lead, the lift and the aim lift as ramps over the
*clock*. They are really statements about the *course*. Under a breathing clock
those diverge, and worst exactly where it matters: the arrival crawls, so at
`u = 0.9` the flight is already 95.4 per cent of the way down the corridor. Read
on the clock the lift ramp is still at 15.1 there; read on the course it is at
11.9, on its way to the authored 10. Left on the clock the lens would sit three
units higher over the start machine through the whole arrival — and the tail
knot of 10 exists precisely because 26 made the handoff a plan view.

So `warp()` resamples each ramp's knots onto the paced clock. The endpoint knots
are fixed points, so `cam_from` and `cam_to` do not move at all; the worst
resampling error over the three ramps is 0.024 layout units.

## The handoff, and two defects it turned up in V22

The brief asks for the preview to settle into the V22 chase's starting pose, and
for the residual motion to be measured. Measuring it found that V22's handoff is
not as exact as its own docstring says.

### 1. Arriving at rest is not arriving continuously

`course_preview._blend_end` eases the tail onto one fixed pose with a
smootherstep, so its velocity at the last frame is exactly zero — V22's landing
measures 3e-05 layout units in its final frame. But the camera that takes over is
**already moving 0.169 layout units a frame**, orbiting the machine at
`chase_camera.START_BEARING`. A preview that arrives at rest therefore hands over
with a velocity step of the whole 0.169, and a gaze-rate step of the whole
0.377 degrees.

`Rail` closes it. The tail is eased onto the race camera's own track *continued
backwards in time*: the orbit is read in cylindrical coordinates about its fixed
aim and reflected through frame zero, which is exact for an orbit about a fixed
point. Frame −1 of the preview is then where the chase camera would have been one
frame before the film starts.

| | V22's landing (`land="still"`) | this pass (`land="rail"`) |
|---|---|---|
| pose delta at the cut | 0.000000 | 0.000000 |
| aim delta at the cut | 0.000000 | 0.000000 |
| preview's last step | 0.00003 | 0.16967 |
| race camera's first step | 0.16945 | 0.16945 |
| **velocity residual** | **−0.16942** | **+0.00022** |
| **gaze-rate residual** | **−0.37697** | **−0.00001** |

### 2. The same pose, a different lens

V22's last preview row and the race's first row carry the same position and the
same aim to four decimals — and **48 degrees of field of view against 34**. The
renderer takes the field of view from the row it is playing
(`sloped_race_scene.gd:461`), so the film cuts from a 48-degree lens to a
34-degree one on a frame where nothing else changes: a zoom snap of 1.45× in the
image. Nothing in the V22 report looks at the eighth column, so nothing caught
it.

It is closed the same way, over the last 40 frames, and what it buys besides
continuity is a move: a wide lens that tightens onto the machine as the flight
settles, which is what "arrive behind the racers" looks like. The final frame's
`fov_delta` is 0.000.

The consequence of the two together is that **the preview's last frame and the
film's first race frame are now the same picture** — same pose, same aim, same
lens, and the frozen replay the preview renders against *is* race frame 0.

### 3. A grazing sight line the extra frames found

At 3.2 s, frame 142's sight line passes through the start module 23.73 units
along its 26.83 — 3.10 units short of the aim, and so 0.10 inside the 3.00-unit
window `check_preview` looks in. V22 does not trip it because at 120 frames it
has no frame there. Raising the aim-lift tail knot from 2.5 to 3.0 takes the
count to zero at all three durations for 0.003 degrees of extra gaze turn.

## The candidates

All three are the same flight on three clocks: same corridor, same composition,
same lighting, same V21 readability pass, same seed 5432, same frozen replay.

```
                                    28          32          35
  --------------------------------------------------------------
  duration (s)                   2.783       3.183       3.483
  frames                           168         192         210
  prefix (s)                     2.800       3.200       3.500

  max camera step                1.265       1.107       1.013
  mean camera step               0.631       0.554       0.507
  max across / rise          0.28/0.65   0.24/0.57   0.22/0.52
  max angular step               0.886       0.800       0.742
  max yaw / pitch            0.57/0.81   0.50/0.70   0.46/0.65
  straight-track rate            1.229       1.074       0.982
    (V22's own peak)             1.074

  track in frame, mean           0.438       0.440       0.441
  track in frame, worst          0.062       0.062       0.062
  ground clearance                3.24        3.09        2.98
  lens clearance                 12.22       12.22       12.22
  centre blocked (frames)            0           0           0

  landmark screen time, as the subject of the shot
      finish                     0.417       0.483       0.517
      merge                      0.383       0.433       0.483
      branches                   0.250       0.283       0.300
      fork                       0.350       0.400       0.450
      obstacle                   0.383       0.433       0.483
      turns                      0.300       0.350       0.383
      mixer                      0.300       0.350       0.367
      start                      0.417       0.467       0.517
      split (branches+fork)      0.600       0.683       0.750

  handoff
      last step / race first   0.170/0.169 0.170/0.169 0.170/0.169
      velocity residual       +0.00022    +0.00022    +0.00022
      turn residual           -0.00001    -0.00001    -0.00001
      pose / aim / fov delta   0.000       0.000       0.000
      slowest step in settle    0.0868      0.0649      0.0527
```

Against the V22 baseline, the high-priority landmarks at 3.5 s: the split goes
from 0.350 s to 0.750 s, the obstacle from 0.217 to 0.483, the fork from 0.217 to
0.450, the start from 0.233 to 0.517. The low-priority mixer goes from 0.333 to
0.367 — a tenth of the growth the fork gets, on a shot 1.75 times as long. That
ratio is the pass.

### The rendered frames agree

`tools/sloped_v221_preview.py qc` measures the mean absolute luma difference
between consecutive rendered frames, downsampled to 270×480 first, and asks
whether any pair is the same picture and whether any step stands above its
neighbourhood as a hitch:

| candidate | frames | min | mean | max | worst spike | duplicates |
|---|---|---|---|---|---|---|
| preview_28 | 168 | 3.40 | 15.28 | 28.80 | 1.18× | none |
| preview_32 | 192 | 3.31 | 14.18 | 26.20 | 1.15× | none |
| preview_35 | 210 | 3.07 | 13.46 | 25.12 | 1.24× | none |

The minimum is never near zero, which is the answer to "does the settle stall in
the picture": it does not. The spike ratios are well inside the 1.6 bar, which
includes the frames where the field of view is ramping.

## Recommendation: **preview_35, 3.5 s, 210 frames**

It is the only candidate that passes its own bar with nothing outstanding.
`preview_32` fails one clause — the straight-track rate, by three decimals — and
`preview_28` fails four. Judged on the pictures rather than the numbers, the
3.5 s cut is also the one where the branches still read at 270 px: 0.300 s is
thin, and 0.250 s at 2.8 s is back inside V22's failure.

The cost is 1.5 s added to the film's 23.05 s.

## Weaknesses, honestly

1. **The last third of the flight is dominated by the start complex.** As the
   reverse dolly retreats past the start machine, the shuffle rotor fills the
   foreground while the `turns` the gaze is on sit small in the mid-distance.
   The `turns` and `mixer` windows therefore buy less recognition than their
   numbers suggest — though what they show instead is the start machine, which
   is high priority, so the time is not wasted. This is inherent to the camera
   language the brief asked to preserve, not to the pacing.
2. **`branches` never reaches its own floor alone** (0.300 s at 3.5 s). Its
   segment is bounded by the midpoints to `merge` and to `fork` and is 6.9 units
   of corridor wide — the narrowest of the eight — so no pacing short of a stall
   gets it there. It is checked as one subject with the fork, which is how the
   brief lists it ("split / two routes"), and the pair gets 0.750 s.
3. **Mean track-in-frame falls from V22's 0.454 to 0.441.** The field-of-view
   landing is the cause: a 34-degree lens at the end holds less of the ribbon
   than a 48-degree one. It is a deliberate trade for the handoff and for a
   tighter arrival on the eight racers, but it is a real loss.
4. **The settle is not monotone.** The static blend brings the flight nearly to
   rest and the rail correction brings it back to 0.169; between them the
   slowest step is 0.053 (3.5 s). `RAIL_HORIZON` trades that dip against tilt —
   60 frames is the last horizon that costs no tilt at all. The rendered QC says
   the dip is not visible (minimum inter-frame difference 3.07 against a mean of
   13.46), but it is a residual and not a zero.
5. **The three candidates share one pacing design.** Only `seconds` varies, which
   is what makes the comparison clean, but it also means no candidate was tuned
   *for* 2.8 s. A 2.8 s cut with less dwell would pass the straight-track bar —
   at the price of the landmark floors, which is the trade the pass exists to
   refuse.
6. **`finish_overrun` moved from −6 to −2.** V22 chose −6 to keep the gaze off
   the finish gantry. Measured against the drawn course, `centre_blocked_frames`
   is 0 at every overrun from −6 to 0 and the lens never comes within 12.2 units
   of any solid. −2 keeps two units of standoff because the block test shortens
   its ray by 3 units and so cannot see a solid sitting exactly on the aim. This
   is a composition change, small but real, and it is what makes the finish a
   0.52 s subject instead of a 0.23 s one.

## Integration, when it is wanted

Verified against the V22 files rather than guessed at. Three edits, none of them
to the race:

1. **`sloped/v22.py`.** `PREVIEW` becomes `v221_preview.preview_spec(PREVIEW)`
   with a `Pacing(seconds=3.5, name="preview_35")` beside it, and
   `build_preview_track` calls `v221_preview.build(..., rail=Rail(race_track
   ["cuts"][0]["frames"]), land="rail")` and **`v221_preview.preview_track`**
   rather than `course_preview.preview_track`. The last of those is not
   cosmetic: the shipped writer puts one constant in the field-of-view column,
   which is the zoom snap described above.
2. **`tools/sloped_v22.py`.** `stage_freeze` already takes its length from the
   track; `_assert_handoff` should gain the eighth column, since it currently
   compares the six pose numbers and would pass a 14-degree lens mismatch.
3. **The V22 integration tests.** `tests/test_sloped_v22_integration.py:59` pins
   `PREVIEW_FRAMES = 120`; it becomes 210 and `PREVIEW_PREFIX` follows to 3.500.
   Nothing else in `tests/test_sloped_v22_*.py` depends on the preview's length.

Two things that look as though they need changing and do not:

* **`tools/sloped_short.py`** derives the clock's prefix from the preview
  master's own frame count (`prefix = master_frames(preview) / FPS`), and PICK
  ONE's cues are already written as `prefix + PICK_ONE_IN`. A longer preview
  master therefore moves every cue by exactly 1.500 s with no code change at
  all. Only the two comments that say "120 frames" go stale.
* **`sloped/v22_timeline.py`** is the *race's* pacing model and never reads the
  prefix. It is untouched.

`preview_prefix` also needs no change: it is already frames over fps, and
210 / 60 is 3.500 exactly — the arithmetic trap `sloped/v22.py`'s docstring
warns about (the report's 3.483 is the span of frame centres) is still the trap,
and this pass writes 3.500 into `report["prefix"]` for the same reason.

## Files

| file | what |
|---|---|
| `sloped/v221_preview.py` | the pacing density, the clock, the warp, the rail handoff, the report and the bar |
| `tools/sloped_v221_preview.py` | solve / stills / clip / qc / sheet / phone for the three candidates |
| `tests/test_sloped_v221_preview.py` | 22 tests |
| `docs/validation/sloped_race_v1/v221_preview/` | the contact sheets |

Proofs (generated output, not in the branch):

* `output/sloped_race_v1/preview_28_v221.mp4`
* `output/sloped_race_v1/preview_32_v221.mp4`
* `output/sloped_race_v1/preview_35_v221.mp4`
* `output/sloped_race_v1/preview_35_v221_phone.mp4` — 270×480
