# V24: making the marbles' real rotation visible

**Branch** `v24-visible-marble-spin`, from `main` at `e697a12` (V22.1).
**Status** a lab proof, awaiting review. Nothing is installed in the film.

The report asked whether the marbles slide through the ShuffleFloor mixer, and
was explicit that the answer must not be assumed. It is not a physics fault.
The solver rotates every marble, the replay records it, and the renderer
applies it correctly. The picture cannot show it because the thing being drawn
is a uniformly coloured sphere.

---

## 1. The diagnosis

### The replay rotates

`sloped/v24_spin.py` measures the seed 5432 replay (`race_5432.json`, digest
`aafb0d3d…`, the one `test_sloped_v221_shuffle` already locks). Angular speed
is reported two ways: PyBullet's recorded `w`, and the angle between the
recorded orientations of consecutive frames. They are independent records, and
if the renderer were being fed a stale orientation beside a live velocity only
one of them would be large.

| phase | replay s | \|w\| median | p95 | max | step median | turns/s |
|---|---|---|---|---|---|---|
| mixer | 1.00–5.50 | 2.12 | 16.98 | 26.49 | 2.03°/frame | 0.34 |
| spin-down | 5.50–6.00 | 1.08 | 3.64 | 3.64 | 1.03°/frame | 0.17 |
| release | 6.00–7.00 | 15.51 | 41.11 | 49.94 | 14.96°/frame | 2.47 |
| descent | 7.00–12.00 | 87.28 | 118.90 | 154.25 | 83.35°/frame | 13.89 |
| obstacle | 13.80–15.10 | 7.84 | 26.65 | 42.36 | 7.66°/frame | 1.25 |
| fork | 15.10–16.73 | 18.05 | 88.64 | 104.99 | 17.61°/frame | 2.87 |
| rolling | 17.00–19.00 | 53.57 | 90.97 | 105.92 | 51.24°/frame | 8.53 |
| final | 19.00–21.00 | 51.44 | 93.35 | 109.23 | 49.12°/frame | 8.19 |

Speeds are rad/s. The two measures agree to within 5% throughout, so the
quaternions in the replay are live.

Per marble in the mixer (1.0–5.0 s), median \|w\| ranges 0.72–5.51 rad/s and
every one of the eight peaks above 18 rad/s. **No marble is inert.**

### The renderer applies it

`sloped_race_scene.gd` sets `node.quaternion` in exactly two places, and both
read the replay's own `q`:

    node.quaternion = _quat(a["q"]).slerp(_quat(b["q"]), blend)

There is no term anywhere in the scene deriving rotation from linear velocity,
and `test_the_renderer_takes_orientation_straight_from_the_replay` holds that.

**The sampling is honest.** Godot's `slerp` takes the short path, so a marble
turning more than 180° between two replay frames would be drawn rolling
*backwards*. The maximum over the whole race is 145.87° (at replay 9.52 s) and
nothing exceeds 180°. The replay is above Nyquist for its own rotation.

### So what is wrong

A uniformly coloured sphere is invariant under every rotation. The measure that
matters is therefore not an angular speed but **how much of the marble's
visible face changes between frames** — `visible_change()` samples the lit
hemisphere, weights by foreshortening, carries each sample into the marble's
own frame by that frame's orientation, and asks what it lands on.

For the shipped appearance that number is **exactly 0.0, on every pair of
frames, for every marble, in every phase.** Not small — zero, by construction.
That is the whole fault, and it is a surface fault.

---

## 2. What was built

`godot/assets/marble_machine/racers/racer_visual.gd` — a racer visual builder
with four appearances: `solid`, `ribbon`, `crescent`, `meridian`.

**The marker is a texture, not geometry.** It is painted into the racer
material's albedo map, which lives in the mesh's local UV space and is
therefore carried by the node transform exactly. There is no child node, no
second transform, and nothing to animate.

**The map is a multiplier.** Godot multiplies `albedo_color` by
`albedo_texture`, so a map that is white leaves the shipped racer colour
bit-for-bit unchanged. Every appearance is white everywhere except on the
marker. Body hue, saturation and value of all eight racers are untouched.

**The marker is greyscale, so all eight racers share one 512×256 texture.** A
grey multiplier darkens without moving hue — which is both what a swirl inside
a candy marble looks like and why this costs one image for the whole field.

`solid` builds no texture at all and returns the palette's own material
*object*, so the default appearance is not a reconstruction of what shipped —
it is the shipped thing.

The renderer hook is one edition-gated flag, `--racers=`, defaulting to
`solid`. Every film through V22.1 re-renders exactly what it shipped.

### The UV convention is verified, not assumed

The marker shapes are defined in 3-D and painted by inverting Godot's
`SphereMesh` UV layout. `godot/scripts/sphere_uv_check.gd` checks that
inversion against the mesh the engine actually builds: worst offset over 350
vertices is **8.4e-8**. It also confirms the ribbon really is a great circle
and that `solid` is featureless.

`godot/scripts/racer_visual_check.gd` dumps the GDScript's own coverage values
at 512 directions; the Python twin used for every number in this report matches
them to **3.5e-6**.

---

## 3. The three variants

| | shape | marker share of the ball |
|---|---|---|
| **A ribbon** | one thin great circle, tilted off every axis | 8.7% |
| **B crescent** | a spherical cap with an offset cap bitten out | 4.1% |
| **C meridian** | the great circle plus a small circle about a second axis | 14.3% |

Visible marker change per frame, from the real V22.1 camera (median / p95 /
share of frames where the marking says nothing):

| moment | solid | ribbon | crescent | meridian |
|---|---|---|---|---|
| mixer spin-up | 0.000 / 0.000 / **100%** | 0.088 / 0.200 / 0.0% | 0.008 / 0.125 / **40.1%** | **0.151 / 0.292 / 0.0%** |
| mixer full | 0.000 / 0.000 / 100% | 0.015 / 0.032 / 0.7% | 0.003 / 0.017 / 44.6% | **0.025 / 0.052 / 0.7%** |
| trapdoor | 0.000 / 0.000 / 100% | 0.100 / 0.208 / 0.6% | 0.014 / 0.152 / 33.0% | **0.153 / 0.321 / 0.0%** |
| descent | 0.000 / 0.000 / 100% | 0.179 / 0.212 / 0.0% | 0.065 / 0.175 / 6.1% | **0.260 / 0.338 / 0.0%** |
| obstacle | 0.000 / 0.000 / 100% | 0.056 / 0.173 / 0.2% | 0.013 / 0.079 / 26.4% | **0.084 / 0.238 / 0.2%** |

**Recommended: `meridian`.**

* **`crescent` is falsified.** A single patch is on the far side of the ball
  much of the time: it says nothing in 33–45% of mixer frames, and the mixer
  filmstrip shows most marbles reading as plain. The brief wanted "less
  visually busy"; this is less visible, which is a different thing.
* **`ribbon` works** and is the most restrained. Its one weakness is structural
  and worth stating: a single great circle has an axis it can turn about
  invisibly. In this race that costs almost nothing (quiet share ≤0.7%), but it
  is a property of the shape rather than of this seed.
* **`meridian` never goes quiet**, because no rotation leaves two circles about
  different axes both stationary. It carries roughly 1.5× the ribbon's signal
  for 14.3% coverage, and still reads as a swirl rather than a marking.

---

## 4. Proofs

Under `output/sloped_race_v1/v24/spin/clips/` — full resolution 1080×1920 and
a 270×480 downscale of each, four appearances per moment including the control:

| clip | replay s | film s |
|---|---|---|
| `mixer_spin_up_*` | 0.80–2.00 | 0.60–1.80 |
| `mixer_full_*` | 4.05–5.25 | 1.90–3.10 |
| `trapdoor_*` | 5.95–7.05 | 3.80–4.90 |
| `descent_*` | 8.40–9.60 | 6.25–7.45 |
| `obstacle_*` | 13.80–15.00 | 11.65–12.85 |
| `omission_*` | spans the cut | 1.35–2.35 |

Close crops (`docs/validation/.../strip_*.png`) are cropped from the camera by
projection, not by eye, so the control and each variant are cropped identically
by construction.

### Mixer review

Yes. In `strip_mixer_spin_up_meridian.png` each marble carries a band that
changes orientation tile to tile while the ball also travels; the control strip
beside it shows eight featureless discs sliding. The motion is translation **+**
rotation **+** contact-driven changes of axis, and it is plainly not a texture
spinning at a constant rate — the marbles that are wedged against the wall turn
slowly while ones crossing the bowl tumble.

### Rolling review

Outside the mixer the roll direction matches travel, marbles that bounce off
the obstacle change spin axis on contact, and airborne marbles hold their axis.
None of this is imposed: it is the recorded angular velocity, which the
measurements above show is what the marking is following.

### Phone size

Measured rather than eyeballed: frame-to-frame luma change inside the marble
discs after reduction to 270×480. A plain marble already changes those pixels
(it is travelling, and the light on it changes) — that is the floor, and what a
marked marble scores above it is what the marking contributed.

| moment | solid (floor) | ribbon | crescent | meridian |
|---|---|---|---|---|
| mixer spin-up | 7.22 | +1.70 | +0.94 | **+2.51** |
| mixer full | 7.03 | +0.57 | +0.08 | **+0.83** |
| trapdoor | 6.63 | +0.69 | +0.35 | **+0.93** |
| descent | 23.59 | +1.80 | +0.80 | **+2.61** |
| obstacle | 13.62 | +0.80 | +0.26 | **+1.23** |

The marking survives the downscale everywhere, and `meridian` leads at every
moment. The descent floor is high because translation dominates at that speed;
the marking still adds 11% on top of it.

---

## 5. The shuffle omission — a finding

V22.1 omits replay **2.050 → 4.000 s** (1.95 s) at output 1.850 s.

**The plain sphere was hiding an orientation discontinuity, and the marking
exposes it.** Across the cut the marbles turn a median 119.7° (max 153.5°),
against 1.77° for an ordinary frame there. Three of the eight turn a long way
while barely moving at all:

| marble | turns | moves (sim units; its own radius is 0.5) |
|---|---|---|
| 0 | 114.0° | 0.127 |
| **1** | **153.5°** | **0.011** |
| 3 | 117.8° | 0.031 |
| 2, 4, 5, 6, 7 | 86.9–144.3° | 0.29–1.12 |

Marble 1 changes face by 153° while moving 1% of its own diameter. Measured
through the real camera, the marking changes **5–6× more across the cut than at
the p95 of an ordinary frame** in the shot that follows.

No interpolation has been faked across the omitted time.

### Can a different boundary do better?

61 whole-frame alternatives were scanned, each sliding **both** ends by the
same offset so every candidate omits exactly 1.95 s — the film's duration and
every downstream time are untouched. 25 keep the machine no worse than shipped.

The best is **offset −28 frames (replay 1.5833 → 3.5333)**:

| | shipped | candidate −28 fr |
|---|---|---|
| rotor phase error | 12.45° | **0.00°** |
| gate paddles / floor panels | 0.00° | 0.00° |
| stillest marble moves | 0.011 | **0.498** |
| …while turning | 153.5° | 92.7° |
| median turn | 119.7° | 91.7° |
| **visible marker jump** | 0.259 | 0.266 — *no better* |

**The honest conclusion is that sliding the join cannot fix the orientation
jump, and the candidate is not offered as if it could.** The visible-change
measure saturates above about 20–25° of turn: below that it grows with the
angle (which is why an ordinary mixer frame reads as *turning*), above it the
marking is simply somewhere else on the ball and a further 90° adds nothing
anyone can see. Every candidate omits ~2 s of mixing and so turns the field far
past that knee.

What the candidate *does* fix is real but narrower: the rotor lands on exact
phase instead of 12.45° off, and no marble changes face while holding its
place — which is the case that reads as a fault rather than as a cut.

Two further observations:

* **The camera is still most of the join.** The frame pair
  (`join_meridian.png`) shows the composition moving substantially across the
  cut; the orientation change sits inside a much larger one. This agrees with
  the V22.1 shuffle-continuity finding that the camera was 93% of the "jump".
* **The decorative shuffle paddle wheel is 74.46° out across the cut**, which
  on a 4-blade wheel is a visible 15.5° step. It is **identical under both
  boundaries** and is present in delivered V22.1 — this work neither causes nor
  changes it, but it is the one machine part the omission is not phase-locked
  on.

**Nothing about the production V22.1 timeline was changed.** The candidate is
reported, not installed.

---

## 6. Performance

Measured by rendering the same 73-frame window four times at 1080×1920:

| appearance | ms/frame | vs solid | mesh instances | triangles |
|---|---|---|---|---|
| solid | 481.8 | — | 1561 | 556 728 |
| ribbon | 491.6 | +2.03% | 1561 (+0) | 556 728 (+0) |
| crescent | 483.1 | +0.27% | 1561 (+0) | 556 728 (+0) |
| meridian | 492.3 | +2.18% | 1561 (+0) | 556 728 (+0) |

**Zero extra mesh instances, zero extra triangles, one extra texture for the
whole field.** The ~2% spread is within run-to-run noise on a 73-frame sample
(the same appearance varies by more than that between the perf and clip runs:
`meridian` measured 492 ms here and 485–606 ms across other windows). There is
no geometry to be slow.

Racer material count is unchanged at eight; `solid` shares the palette's cached
materials exactly as before.

---

## 7. Country skins

Not implemented, as instructed. The mechanism is already the right one: a
country skin is a texture, it enters at the same single `albedo_texture` line a
band enters at, and it therefore inherits the replay quaternion for exactly the
same reason. It needs no new node, no new transform and no contact with the
physics. `test_a_country_skin_would_inherit_the_same_transform` holds that
entry point at one place.

---

## 8. Tests

`tests/test_sloped_v24_spin.py`, 27 tests. The full suite is 2060 tests, one
pre-existing failure unrelated to this work (`test_neon_proof.py::
test_a_missing_godot_is_reported_rather_than_raised` — that tool reports a
missing neon replay before it reaches the Godot path, and this worktree has no
generated neon output).

What they hold:

* the replay is still seed 5432's race — digest, seed and finishing order
* every marble rotates in the mixer, and recorded orientation agrees with
  recorded angular velocity to within 10%
* no marble turns more than 180° between replay frames
* the renderer takes orientation only from the replay's `q` — no velocity term
* **no synthetic spin law exists**: nothing in `racer_visual.gd` mentions
  `delta`, `Time.`, a frame index, a velocity or any animation type
* a frozen quaternion gives a frozen marking; a turned body turns the marking
  with it, exactly
* `solid` is featureless, is still the default, and returns the palette's own
  material object
* the builder adds no children and no geometry
* the Python twin matches the GDScript it describes to 1e-4
* the shuffle omission is where V22.1 put it; its orientation jump is locked so
  a later edit cannot quietly worsen it; every scanned candidate omits exactly
  as much replay time; and the marking saturates, so a slide cannot fix it
