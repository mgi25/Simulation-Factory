# V33.1 — the post-finish run-out, laid along the track and sized to the shot

**Branch** `v331-runout-fix`, from `origin/v33-mobile-race-bookends` at `749d355`.
**Scope** one geometry defect in one module. No creative pass, no V33.2 redesign.

V33 is Test #4's candidate and everything about it works except the last three
seconds. This document is the repair of those three seconds and the proof that
nothing else moved.

The brief named one change — rotate the run-out into line with the track. That
turned out to be necessary and not sufficient, and section 7 is the
measurement that says so. Three other things had to move with it, all of them
inside the same module, and each is a defect the rotation *uncovered* rather
than one it caused.

---

## 1. The defect

The winner of Test #4 does not finish the race. It crosses the line at
15.8167 s, falls for seven frames, and then hangs motionless in mid-air —
1.75 layout units below the running surface it was on — for the last **192
frames of a 1150-frame film**. Three of the eight racers leave the machine:

| racer | crosses | leaves the machine |
|---|---|---|
| m7 — the winner | 15.8167 s | 15.9292 s |
| m1 | 16.1333 s | 16.2375 s |
| m4 | 18.7500 s | 19.1792 s (after the film ends) |

The V33 replay records these as `escaped` events with the machine's own
`failure` string set: *"marble 7 left the machine at (-26.95, -4.13, 40.82)."*
`MarbleSimulation._retire` zeroes an escaped marble's velocity and removes its
body from the world, and the replay writer then repeats its last pose to the
end of the file. That repetition is what is on screen.

Over the film window V33 leaves **367 frozen racer-frames** — racer-frames in
which a retired marble repeats a pose it can no longer leave. The winner is
supported by the run-out for **none of the 201 frames** after it crosses: it
misses the deck entirely and falls past its edge.

---

## 2. The cause: two yaw conventions, ninety degrees apart

`race2.parts.RunOut.__init__` built the deck's frame like this:

```python
yaw = math.radians(sprint.heading_deg(exit_index))
self.forward = (math.cos(yaw), 0.0, -math.sin(yaw))
```

Two different angle conventions meet on those two lines, and they do not agree.

**`sloped.track.TrackRun.heading_deg`** is a compass heading, `atan2(x, z)`.
Zero is +Z, +90 is +X, and the direction of travel for a heading `h` is
`(sin h, 0, cos h)`. That is exactly the third column of
`sloped.stations._yaw_frame(h)` — the basis Godot gives a node yawed by `h` —
which is why it is the angle a *built* thing takes. Race #1's own
`sloped.stations.FinishDeck` is the correct consumer: it calls `_yaw_frame`
and takes `along = az`.

**`race2.kit.Frame.yaw`** and `marble3d.geometry.Socket.heading` are the
engine's yaw, `atan2(-z, x)`. Zero is +X, +90 is −Z, because
`marble3d.geometry.yaw_quaternion` rotates +X toward −Z, and the direction of
travel is `(cos y, 0, -sin y)` — the *first* column of the same basis.

`RunOut` took a compass heading and read it with the engine's forward formula.
That is not a bug that is small at some bearings and large at others:

```
(sin h, 0, cos h) · (cos h, 0, -sin h)  =  sin h cos h − cos h sin h  ≡  0
(sin h, 0, cos h) × (cos h, 0, -sin h)|y =  cos²h + sin²h              ≡  1
```

The dot product is **identically zero** and the cross product's +Y term is
**identically one**. The deck was turned exactly ninety degrees from the
direction of travel at every heading there is. `RunOut` was reading the frame's
local **+X** where it needed the local **+Z**.

### What that did to SWITCHYARD

The sprint exits at heading −90° — travel is −X — at layout `(-12.5, -0.6, 24.0)`:

| | direction | what ran along it |
|---|---|---|
| true travel | `(-1, 0, 0)` | — |
| `RunOut.forward` (shipped) | `(0, 0, +1)` | `DEPTH` = 8.2, the run-out length |
| `RunOut.across` (shipped) | `(-1, 0, 0)` | `WIDTH` = 11.0, the pack's spread |

The deck's 8.2 units of run-out ran off sideways into +Z, and its 11 units of
width ran *along* the track — 5.5 of them *upstream* of the finish line. The
deck's near edge, at `along = 0`, lay along the racing line itself. A racer
that drifted even slightly to −Z of the centreline was over nothing. The winner
did: it escaped at layout `z = 23.27`, 0.73 units to the wrong side of an edge
that was directly under the racing line.

`RunOut` has been wrong since the commit that wrote it — `8daff3a`, the one
that introduced SWITCHYARD — so every Race #2 film from that point on has the
defect. V33 diagnosed it and did not repair it (`race2/bookends.py`, the module
note; `tools/race2_v33_bookends.py::stage_field`), because its brief locked the
physics. V33.1's brief does not.

---

## 3. The canonical rule

One conversion, written once, in `race2/kit.py` beside `Frame` — the type that
owns the other convention. The note there carries the arithmetic above; the
callable part is:

```python
flat_forward(direction)         # a tangent, flattened to the ground and normalised
forward_from_heading(deg)       # compass heading  -> direction   (sin h, 0, cos h)
heading_from_forward(direction) # direction -> compass heading    atan2(x, z)
build_yaw_from_forward(dir)     # direction -> Frame.yaw/Socket.heading, in degrees
frame_along(origin, forward)    # frame_towards' sibling, from a direction not two points
```

`build_yaw_from_forward(f) ≡ heading_from_forward(f) − 90°`, exactly, and a
test asserts it at 121 bearings.

**The rule is: prefer a direction to either angle.** A tangent differenced off
a path cannot express this mistake at all. `race2.bookends.site_from_run`
already worked this way and was never wrong; `RunOut` now does too, and a test
parses its source to make sure no later edit puts a heading back.
`forward_from_heading` exists for callers that are *handed* an angle and have
no tangent — it is the only place the conversion is written.

---

## 4. The change

Six edits. One is the brief's fix; four are defects the fix uncovered or
introduced, each of which would have shipped as a bug; one is a report that
could not come back clean.

### 4.1 `race2/parts.py` — the deck's frame

```python
-        yaw = math.radians(sprint.heading_deg(exit_index))
-        self.forward = (math.cos(yaw), 0.0, -math.sin(yaw))
+        self.forward = flat_forward(sprint.tangents[exit_index])
         self.across = (-self.forward[2], 0.0, self.forward[0])
```

The deck, its back wall, its two side walls, its fall, its probes and its
sockets are all built off `forward`, so correcting one expression rotates the
whole module into place.

### 4.2 `race2/parts.py` — the finish gate, behind the wall rather than in front

`MarbleSimulation` takes the last module's `exit` socket as the machine's
finish gate and retires anything that reaches it. That socket stood at
`DEPTH - 0.2` = 8.0, while a marble resting against the back wall centres at
`DEPTH - MARBLE_RADIUS` = 7.915. **The gate was 0.085 layout units in front of
the resting place**, so the back wall could never stop anybody: everything that
reached the back of the deck was captured just before it touched, frozen, and
removed from the world.

With the deck across the track this never fired — the field fell off the side
first — so the defect was invisible. With the deck the right way round, m1 ran
the length of the deck and was frozen at 16.4 s, 0.27 s after crossing. The
socket now sits at `DEPTH + CATCH` with `CATCH = 0.60`, a little over one
marble diameter (0.57) past the wall's inner face.

### 4.3 `race2/parts.py` — `DEPTH` 8.2 → 3.2, sized to the camera envelope

Section 7 has the measurement. The finish shot pulls back through the payoff,
and what it can still hold collapses quickly. For a racer *at rest* to be in
frame for every frame of the settled window:

| resting `along` | widest \|across\| held for the whole window |
|---|---|
| 3.0 | **±6.0 — the entire deck** |
| 3.4 | ±4.3 |
| 3.8 | ±0.9 |
| 4.0 and beyond | nothing |

A racer comes to rest about a radius short of the back wall, so `DEPTH` 3.2
puts the field at 2.9 — inside the band where **every** part of the deck it can
reach is on screen. That is what makes the number robust: it does not depend on
which way the pack happens to scatter, and the pack's lateral outcome is
chaotic (it flipped from −4.3 to +4.9 when the wall's triangulation changed).
At 8.2 the winner was on screen for 95 of the 200 frames after it crossed.

**This is not the number a scan would have picked.** Scanning depths for
"winner on screen 200/200" returned 4.0, 4.2 and 4.8 but not 4.4 or 4.6, and
the answer moved when the mesh changed — because at those depths the field
rests in the corner where being in frame depends on which side it lands. Inside
the envelope every depth from 3.0 to 3.6 scores 200/200. The envelope is the
reason; the score is the confirmation.

### 4.4 `race2/parts.py` — `RIM` 0.80 → 2.00, sized to a bounce that does not converge

A racer arrives at about 29 layout units a second and is stopped by the back
wall. At `RIM` 0.80 the wall was lower than the rebound it caused — a marble
coming off it 0.55 has its centre at 0.83, over the top — and the consequence
was a **coin toss on contact timing**: at `DEPTH` 4.8 and 5.6 the winner
cleared the wall and was retired through the gate behind it, while 4.6, 5.0 and
5.2 held it, with no trend between them.

Raising the rim does not tame the bounce; it contains it. The worst rise in the
field over `DEPTH` 3.0 to 3.6 runs 1.26, 1.11, 0.78, 0.86, 1.82, 1.21 — no
trend, and it moved again when `_wall_steps` changed the wall's triangulation.
So the rim is not tuned to the shipped depth either: it is set above the worst
centre height seen anywhere in that range, 2.10, and at 2.00 it leaves **0.94
of clearance — more than a marble diameter and a half — above the highest any
racer gets at `DEPTH` 3.2**. Nothing in 3.0 to 3.6 escapes at 2.00.

It is not raised further because there is a ceiling: `wall_strip` never
subdivides vertically, so the rim's own height is a single triangle edge and
`check_mesh` bounds that at four marble diameters. **`RIM` 2.28 is the wall
that cannot be built at all**, and `_wall_steps` raises rather than silently
failing if anyone tries.

### 4.4b `race2/parts.py` — the wall subdivision, derived rather than typed

Raising the rim broke `test_race2_course.py::test_the_meshes_are_well_formed`,
and the failure is worth recording because it was mine, not V33's. A
`wall_strip` cell is `span/steps` wide by the rim's *full* height, so a taller
rim makes a taller quad and a longer diagonal: at the six steps the back wall
had used since it was written, `RIM` 1.60 gave a cell 3.216 by 2.807 and a
diagonal of 4.269, over the 4.000 limit, on geometry that had been well formed
at 0.80 for the same six steps.

`_wall_steps` now derives the count from the span, the rim and
`check_mesh`'s own bound, so the next dimension change does not have to
remember. It is also the reason the physics had to be re-measured: a finer
triangulation is a different contact surface, and it moved the winner's
rebound from 0.60 to 0.96 and its resting side from −4.3 to +4.9. Everything
in this document after that point is measured on the final mesh.

### 4.5 `race2/race.py` — a shared counter

`class Race2(MarbleSimulation)`, and **both** classes kept `self._finish_count`.
The base increments it in `_retire` for marbles leaving through the exit
socket; `Race2` increments it for marbles crossing the line. They were the same
integer.

It never showed because no Race #2 racer had ever reached that socket alive.
The moment the deck worked, one did, and **the placings from fourth onward were
renumbered by one** — the finish-line events came out 1, 2, 3, 5, 6, 7, 8, 9.
`Race2`'s counter is now `_line_count`. On the V33 replay the base counter is
never touched, so the rename is provably a no-op there.

### 4.6 `tools/race2_v33_bookends.py` — a finding that could not come back clean

`stage_field` wrote a hard-coded `"runout_yaw_error_deg": 90.0` and a note
saying the deck is laid across the track. True when V33 measured it, false the
moment it was repaired. It is now computed from the built module
(`_runout_alignment`), so the same stage reports the defect on a branch that
has it and `0.0` on one that does not.

Prose in `race2/bookends.py` asserting the live defect was moved to the past
tense, and `Field`'s defaults — which encoded the sideways envelope — were
updated to the measured forward one. They are defaults only; every build passes
a measured `Field`.

### What was *not* tried, and why

**An upslope.** A run-out that climbs would decelerate the field
gravitationally and gather it, which is what an arrestor bed does and what the
brief's "slows naturally" asks for. Measured at `FALL_DEG` −1.4, −2.0 and −3.0,
it gathers beautifully and then rolls **three to six racers back out of the
machine** through the deck's front edge — which is the channel mouth and has no
wall. `FALL_DEG` stays at +1.4, downhill, and the reason is now written next to
it.

---

## 5. The pre-finish lock

The brief's hardest requirement: the race up to the line must be the race V33
ran. It is, and the claim is made per racer rather than per film.

**Why per racer.** "The frames before the winner crosses are identical" is the
weak form — five racers are still on the course at frame 949, and a deck that
had moved under one of them would first show up later than that and pass. The
test is that *each* marble's record is byte-identical at every frame strictly
before **its own** crossing.

| racer | crossing | identical through | worst drift before its crossing |
|---|---|---|---|
| m7 | f949 | f949 | 0.0 |
| m2 | f953 | f952 | 0.0 |
| m1 | f968 | f968 | 0.0 |
| m5 | f995 | f995 | 0.0 |
| m3 | f1032 | f1032 | 0.0 |
| m0 | f1063 | f1063 | 0.0 |
| m6 | f1069 | f1070 | 0.0 |
| m4 | f1125 | f1126 | 0.0 |

Drift is **exactly zero** — not "small" — for all eight.

* All **316** events strictly before the winner's crossing are identical.
* Frames **0–949** are identical for the whole field.
* All eight `finish_line` events are identical in **id, time and placing**:

  `[(7, 15.816667, 1), (2, 15.883333, 2), (1, 16.133333, 3), (5, 16.583333, 4),`
  `(3, 17.2, 5), (0, 17.716667, 6), (6, 17.816667, 7), (4, 18.75, 8)]`

* Winner **m7 / PINK**. Finish order **[7, 2, 1, 5, 3, 0, 6, 4]**. Replay
  length 2401 frames, `physics_hz` 240, `replay_fps` 60 — all unchanged.
* The control replay still carries the production digests
  (`7510313489368087…`, `51078e8d31e56f53…`).

The brief's named locks, each compared over the window before the line:

| event kind | before the line | identical | note |
|---|---|---|---|
| `release` | 8 | yes | the start gate — all 8, so this is the whole timeline |
| `mechanism_hit` | 32 | yes | mixer, drum, sweep, pair — all 32, the whole timeline |
| `line_choice` | 5 | yes | the route split |
| `module_enter` | 82 | yes | |
| `module_exit` | 82 | yes | |
| `collision` | 107 | yes | |

The `marbles` block (count, radius, mass, start slot) and the solver `config`
are byte-identical, so the racers and the physics they run under are the same
objects.

### The one honest caveat

m2 is identical through f952 and its crossing frame is f953 — the divergence
appears *at* its crossing, not before it. The winner is already rolling on the
corrected deck from frame 950, so from that frame the two solvers integrate
different contact sets and every body in the island picks up floating-point
noise whether or not anything touched it. m2's difference at f953 is **0.004
layout units — seven thousandths of a marble diameter** — and m2 and m7 are
three diameters apart at that instant, so they are not in contact. Its crossing
time and placing are identical. Claiming bit-identity *at* the crossing would be
a claim about rounding; claiming it everywhere before is a claim about the
race, and that is the one that holds.

---

## 6. Post-finish behaviour

| | V33 | V33.1 |
|---|---|---|
| racers retired before the film ends | 3 (m7, m1, m4) | **0** |
| frozen racer-frames | 367 | **0** |
| racer-frames off the deck | — | **0** |
| winner frames supported | 0 / 201 | **184 / 201** |
| winner height at the last frame | **−1.23** | **+0.21** |
| winner speed at the last frame | 0.00, frozen in the air | 0.00, at rest on the deck |

Heights are relative to the deck's own origin plane, in layout units: V33's
winner hangs 1.23 *below* it, V33.1's sits on it. (The two builds are measured
against V33.1's deck, so a deck-relative count like "off the deck" says nothing
about V33; `retired` and `frozen_frames` are the figures that mean the same
thing in both, and `post_finish.json` says which is which.)

The winner decelerates from **47.9 layout units a second at the crossing** to
0.36 by 17.63 s and is at rest from about 18.3 s — 0.9 s before the film ends,
with m4 still to arrive. That is a finish: a racer that runs in, slows visibly
over two seconds, and stops in the receiving bay while the rest of the field
comes home.

All eight run the deck's full length — reach 2.90 to 3.00 against a `DEPTH` of
3.2 — and the field settles inside `along` [0.02, 3.00], `across` [−5.22,
+4.14]. Each racer is on the deck within 0 to 18 frames of crossing (most
within two; the slowest is the winner's own arrival arc). After landing the
largest rise off the surface anywhere in the field is **0.24 layout units, 0.42
of a marble diameter** — there is no post-landing bounce to speak of. The
0.78 quoted in section 4 is the *approach* arc before first contact, and the
rim clears even that by 0.94.

**No hidden winner control.** `race2/parts.py`, parsed to code with comments and
docstrings stripped, contains no marble id, no "winner" and no per-racer branch
— it builds one deck and one gate for everybody — and a test asserts that. The
empirical half is that every racer, not just the winner, runs the deck's length
and is held by it.

---

## 7. The camera envelope — why rotating the deck was not enough

**This is the finding of the pass, and it nearly shipped as a new defect.**

With the deck rotated and nothing else changed, the field ran its designed 8.2
units forward and settled there. The locked finish shot does not see that far.
It pulls back through the payoff, and what it can still hold collapses quickly.
Measured against the shipped camera track, for a racer *at rest* to be in frame
for every frame of the settled window:

| resting `along` | widest \|across\| held |
|---|---|
| 3.0 | ±6.0 — the whole deck |
| 3.4 | ±4.3 |
| 3.8 | ±0.9 |
| 4.0 and beyond | nothing |

The rotation-only build left the winner **off the left of frame from 17.43 s to
the end** — screen x reached −1.98, nearly two frame-widths out — and on screen
for **95 of the 200 frames** after it crossed, against V33's 250/250. V33's
winner is visible only because it is frozen in mid-air exactly where the camera
is pointed; the bug was holding it in shot.

The brief locks the camera, so the geometry has to fit the shot: **a run-out has
to be shorter than the frame, not longer than the field.**

### Two instruments, and the gap between them

A **frustum** count says whether a racer's centre is inside the camera's frame.
It knows nothing about what is in front of it. A **matte** — the same frames
re-rendered with every racer painted as a flat class — counts pixels, so a
racer behind a parapet counts as hidden. Both are reported, because a taller
rim is exactly the kind of change that could pass the first and fail the
second.

| | V33 | V33.1 |
|---|---|---|
| winner in frustum | 200/200 | **200/200** |
| winner on screen (matte) | 250/250 | **249/250** |
| mean racers on screen | 4.476 | **4.872** |
| frames with nobody on screen | 0 | **0** |

The one frame is f953, 0.07 s after the crossing, where the winner passes
behind the near gantry leg and out the other side — locked architecture doing
what it has always done, and V24's payoff lab found both of its winner marks
pointing at a marble behind this same gantry. The test asserts the longest run
of hidden frames is one, not that the total is perfect, because a sustained
loss is the defect and a single frame is not.

The 2.00 rim hides nobody: V33.1 shows *more* of the field, for more of the
time, than V33 did.

*(The first pass at the matte reported the winner invisible in every frame of
both builds. `race2_track_surface.racer_class` writes `round(255·index/7)` into
the red byte — 0, 36, 73, 109, 146, 182, 219, 255 — and reading that byte as
the racer number finds racer 7 nowhere. The instrument was wrong, not the
geometry.)*

---

## 8. What else moved, and what did not

### Geometry
The renderer's own geometry export changes in exactly one place. Every run,
every station, the start module and the actuator list are byte-identical; the
`modules` list differs only at `runout`.

### Camera — unchanged, byte for byte
The film is cut on the V31 readability pass's RB track. It is **copied, never
re-solved**, and the three per-composition tracks V33 derives from it come out
with the same SHA-256 as V33's own:

| composition | SHA-256 (first 16) |
|---|---|
| A | `019769139b70dbf7` |
| B | `ddff11cfa012f9c3` |
| C | `c3cf6a96fb62abb4` |

The one cut V33 rewrites — the opening — is sited on the field's own centroid
read off the replay, and that window is before the line where the two replays
are identical.

### The picture, per cut
The two masters compared frame by frame as PNG digests:

| cut | window | frames differing | worst | where |
|---|---|---|---|---|
| `release` (start + hook) | 0.02–2.23 s | **0 / 134** | — | — |
| `upper` (the chase) | 2.23–9.02 s | **0 / 408** | — | — |
| `middle` | 9.02–12.68 s | **0 / 221** | — | — |
| `run_in` (final chase) | 12.68–19.15 s | 228 / 389 | 68.1% | the run-out |

Frame 0 is identical and so is every frame to **15.35 s** — the start, the
whole of the long chase and the whole of the middle, 921 frames of 1150. The
first difference is inside the final chase, which is the shot the run-out is
in. (At `DEPTH` 4.4 the taller rim clipped the bottom-left corner of the middle
cut for nine frames; at 3.2 the deck does not reach into that shot at all.)

### Start stand — unchanged
36 static parts, 3 moving, nearest racer `0.345` at `fin_6` — the same three
numbers V33's own report carries. The eight bays, the gate, its release time
and the `PICK YOUR COLOR` plate are untouched, and the start cut renders
frame-for-frame identically.

### Finish stand — the art is locked, the receiving area follows the field
Of 64 parts in V33's finish stand, **25 are byte-identical**: the whole gantry
(`gantry_header`, `gantry_cap`, `gantry_accent`, `gantry_lit`, both braces),
all four approach-colonnade portals, and the finish line itself — the
track-integrated warm inlay, its kerbs, caps and posts. Nothing was added.

26 parts moved: the plaza tiles, its rim, ends, plinth and lit strip. The plaza
*is* the receiving area, it is sited on the measured field, and the field now
lies in front of the line instead of beside it. The gantry legs and feet moved
by **0.0002 layout units**, because their feet stand on the plaza and its
measured fall changed in the fifth decimal.

13 parts are gone: 8 plaza tiles (a smaller footprint) and 5 `well_*` parts.
The well was the pit V33 built to dress the hole the field was falling into.
With no hole there is no well, and `Field.well_*` is `None` by measurement, not
by decision. Nearest-racer clearance is **0.320** (V33: 0.314) — slightly
better.

### The marks — the same claim, better placed
`evidence.json` for the delivered Short is identical to V33's in `winner`,
`comeback`, `ring`, `rank_runs`, `hook`, `camera`, `film` and `seed`: the
"PINK WINS / 5TH -> 1ST" card makes exactly the claim Test #4 made, and the
winner's ring tracks the same marble from the same frame.

One field differs, and in the right direction. `race2_v32_short` searches the
lower frame for a dark band to seat the payoff card in. On V33 that search
**fell back** - `"fallback": true`, a 225 px band with a maximum luma of 236.8
under the ink, because the bottom of the frame was full of pit and scattered
racers. On V33.1 it finds a real band: 351 px, `"fallback": false`, maximum
luma 67.9. The card sits on dark floor instead of on highlights.

### Runtime and audio — unchanged
1150 frames at 60 fps = **19.1667 s**. The soundtrack is V32.2's delivered
stream, extracted with `-vn -c:a copy` and muxed with `-c:a copy`. Checked on
the AAC elementary stream rather than on the container, because two MP4s built
at different times differ in their headers whatever the audio is doing:

```
V32.2 shipped   9db89f3a919446215cc9e0afd5122b1acc8d4f3351a5f5c7c2afb9e870f832dd
V33 delivered   9db89f3a919446215cc9e0afd5122b1acc8d4f3351a5f5c7c2afb9e870f832dd
V33.1 candidate 9db89f3a919446215cc9e0afd5122b1acc8d4f3351a5f5c7c2afb9e870f832dd
```

No encoder has touched the sound since Test #3. No new finish cue.

---

## 9. Phone review

The finish comparison sheet is rendered twice — at 300 px tiles and at 135 px,
half the 270×480 delivery review size — over the seven instants the brief
names: final approach, the crossing, +0.2 s, +0.5 s, +1.0 s, the payoff and the
last frame. A 270×480 side-by-side of the whole finish is in
`exports/race2_v331_runout/compare_finish_270x480.mp4`.

At phone size the difference is not subtle. V33's approach and crossing tiles
are identical to V33.1's; from +0.2 s a black rectangle — the well — opens in
the middle of the deck and the field scatters round it, and by the last frame
five racers are spread across a plaza with a pit in it. V33.1 has no pit: the
pack runs forward into the receiving bay and by the last frame the field is
gathered under the gantry.

---

## 10. Tests

`tests/test_race2_v331_runout.py` — 54 tests, none skipped once the lab has run.

**The convention.** Heading round-trip over 51 bearings; `build_yaw ≡ heading −
90°` over 121; the shipped expression asserted perpendicular at 73 — so a
reverting edit is told what it has reintroduced. `RunOut`'s forward axis
against the run's own tangent at four cardinals and two diagonals, at
`dot == 1` with `abs_tol=1e-12` rather than `dot > 0`: the broken build scored
exactly zero at every one of them, and a tolerance loose enough to feel safe
would have been loose enough to miss it. Plus a source check — `ast.unparse`d,
so it reads code and not commentary — that no heading is constructed on the way
to the deck's frame, and a geometric check that the finish gate is behind the
back wall.

**The race.** The control replay pinned to the production digests; the six
locked event kinds one assertion each, plus a check that the gate and mechanism
timelines lie wholly before the line so that comparison is exhaustive rather
than a prefix; the racers' own block and the solver config; winner;
finish order; all eight crossings compared as `(id, time, placing)` triples;
per-racer bit-identity strictly before each crossing; no event before the line
moved; replay length; nobody retired; nobody frozen in the last second; the
winner supported, travelling the deck's length, and not a special case; the rim
containing every bounce the deck causes.

**The film.** Camera tracks by SHA; the per-composition report; only the
run-out module moved; start stand part counts and clearance; every gantry,
approach, line and brace part byte-identical to V33's own build; every bookend
part against every marble centre, on a spec and replay that are a matched pair;
the audio elementary stream by digest; runtime; the per-cut picture lock; the
winner on screen in the matte and in the frustum; delivered stream properties.

### The suite, against the base commit

Run at `origin/v33-mobile-race-bookends` and again here, with the same
artefacts on disk both times:

| | base | V33.1 |
|---|---|---|
| failed | 15 | 18 |
| passed | 2995 | 3045 |

Every one of the three net new failures is a **branch-scope guard from an
earlier brief**, the same family as the eight already failing on the base:

* `test_race2_v32_final.py::test_no_locked_file_moved[race2/parts.py]`, `[race2/kit.py]`,
  `[race2/race.py]` — V32's brief locked those files against its own base
  commit. V33.1's brief requires changing `race2/parts.py` by name.
* `test_race2_v33_bookends.py::test_the_branch_adds_bookends_and_touches_nothing_else`
  — V33's brief added only bookends. This one does not.

And one of the base's fifteen now passes: `test_the_finish_stand_exists`, whose
`well_floor` requirement is the conditional described below.

### Three of V33's own tests changed, and why

* `test_the_run_out_deck_defect_is_recorded_not_fixed` asserted that the deck
  is **square** to the direction of travel, and its docstring said it "fails if
  somebody fixes the module, which would be the right fix in a branch that is
  allowed to move the race, and is not this one." This was that branch. The
  assertion is inverted rather than deleted, so the history of the claim stays
  attached to it, and it is renamed
  `test_the_run_out_deck_points_along_the_direction_of_travel`.
* `test_the_finish_stand_exists` required a `well_floor` — "a pocket for the
  racers the deck drops". There are none to drop, `Field.well_*` comes back
  `None` from the same measurement, and the five parts are not built. The
  assertion is now conditional: a stand with a well must have a floor in it.
  (This test also failed on the base commit, for want of V33's built spec.)
* `test_no_bookend_part_stands_where_a_racer_goes` now skips when V33's built
  bookends are not on disk. Its `spec` fixture falls back to a live
  `bookends.build(course)` with `Field`'s defaults, and comparing that against
  V33's recorded trajectories reports a collision neither build has. The claim
  is carried by V33.1's own suite on its own pair.

---

## 11. Remaining weaknesses

1. **The rebound off the back wall does not converge.** How high a racer comes
   off the wall varies with no trend as the deck is tuned — 1.26, 1.11, 0.78,
   0.86, 1.82, 1.21 over `DEPTH` 3.0 to 3.6 — and it moved again when the
   wall's triangulation changed. The shipped build is well behaved (0.24 of
   post-landing rise, 0.94 of rim clearance) but that is an outcome, not a
   guarantee. What *is* guaranteed is containment: the rim is set above the
   worst value seen anywhere in the range. A run-out that stopped the field by
   distance rather than by a wall would not have this property at all.

2. **The run-out is sized to one camera track.** `DEPTH` 3.2 comes from this
   shot's envelope. A different finish camera would want a different number,
   and nothing in the module knows that — the coupling is recorded in a comment
   and in this document, not in code. A course that re-cuts its finish has to
   re-measure.

3. **The deck is short and the stop is a wall.** 3.2 layout units is about five
   and a half marble diameters; the field arrives at 29 units a second and is
   stopped by a rim rather than run down. It reads as a pack hitting a cushion,
   which is legible and is what the shot allows, but "decelerates visibly" is
   doing some work. The honest statement of the trade is that the locked
   camera's reach and a long, gentle run-out are in conflict, and the camera
   won.

4. **The rim is near a hard ceiling.** `wall_strip` never subdivides
   vertically, so the rim's height is one triangle edge and `check_mesh` bounds
   it at four marble diameters. `RIM` 2.28 could not be built at all. At 2.00
   there is room, but not much, and raising it further to buy more bounce
   margin is not available without changing `wall_strip`.

5. **The winner is behind the gantry leg for one frame** (f953, 1/60 s). Locked
   architecture, not new, and the same gantry has done this before — but it is
   one frame of the winner's crossing beat.

6. **The plaza rim is 0.035 units off a racer's surface** at its nearest
   (`plaza_rim_far`, gap 0.320 against a 0.285 radius). Better than V33's
   0.314, but still a near-touch rather than a margin.

7. **The convention still exists.** This pass wrote the rule down and converted
   the one module that got it wrong; it did not delete either convention.
   `heading_deg` and `Frame.yaw` still both exist and still disagree. The
   protection is `flat_forward` plus the direction test, not the removal of the
   hazard.

8. **One seed.** Everything here is seed 8, the hero. The deck is a static
   collider and not seed-specific, but the settle behaviour, the depth basin
   and the rebound range have only been observed on this field.

---

## 12. Upload recommendation

**Yes — V33.1 is the Test #4 candidate:**
`exports/race2_v331_runout/race2_switchyard_v331_your.mp4`

It is V33's picture with one module turned into line with the track and sized
to its shot. The race before the line is bit-identical for every racer; the
winner, the order and all eight crossing times are the numbers V33 shipped; the
camera, the start, the gantry, the colonnade, the finish line, the audio and
the runtime are carried over unchanged, most of them by digest, and the start,
the chase and the middle render frame-for-frame identically.

What changes is the last three seconds. V33 ends with its winner frozen in
mid-air below a hole, three racers out of the machine and five scattered round
a pit. V33.1 ends with all eight in the receiving bay under the gantry, the
winner among them, having run in and slowed to a stop — and with more of the
field on screen through the payoff than V33 managed.

V33 should not be uploaded. The defect it carries is in the payoff shot.
