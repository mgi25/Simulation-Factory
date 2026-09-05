# Bowl benchmark: physics architecture experiment plan

**Branch** `race-physics-lab` · **base** `0013e73` (Neon V1.1, documentation
correction) · **status** research only, nothing here may be merged into
`race-v1` or `main`.

The question this lab exists to answer:

> Can we achieve convincing marble-machine physics while keeping Python
> authoritative, or should this project move to true 3D rigid-body physics?

It is answered by building two prototypes of the *same* benchmark and
measuring them, not by argument. This document is what they are being built
against, written before either of them existed so that the criteria cannot be
adjusted to fit whichever result arrives.

---

## 1. The current production architecture

```
Python + pymunk 7.3.0
      |
      v
2D authoritative simulation      120 Hz fixed step, no accumulator
      |
      v
deterministic replay JSON        60 fps samples, 3 decimals
      |
      v
Godot 4.7.2                      presentation only
```

The pieces that matter to this study:

**The simulation plane.** `race/simulation.py` builds one `pymunk.Space` with
`gravity = (0, GRAVITY)` where `GRAVITY = 1500` and `+y` is *down* the canvas.
Course geometry is static `Poly` and `Circle` shapes on `space.static_body`
(`race/runtime.py`); a racer is a `pymunk.Circle` on a dynamic body with
`RACER_RADIUS = 30` px and a `velocity_func` that caps speed at 750 px/s.
Spinners are single kinematic bodies. There is no third axis anywhere in it.

**The clock.** `PHYSICS_HZ = 120`, and `RaceSimulation.step()` calls
`space.step(PHYSICS_DT)` exactly once. Nothing accumulates real time; a caller
asks for ticks and gets ticks. That is the root of every reproducibility
property the project has.

**Seeded streams.** `race/seeds.py` derives one `random.Random` per concern
from a salted seed - course, spawn, runtime jitter - so adding a random draw in
one place cannot move another. Jump-pad kicks are applied in racer-id order
(`RaceSimulation._apply_kicks`) precisely so that the order Chipmunk happened
to report contacts in cannot change which jitter value each racer draws.

**The replay.** `replay/race_exporter.py` samples every second tick
(`TICKS_PER_FRAME = 2`) and writes course geometry in full, per-frame spinner
transforms and a per-frame camera track. A renderer rebuilds the world from the
file alone and never imports a course builder.

**The presentation mapping.** `godot/scripts/neon_scene.gd` derives the whole
third axis from one function, `deck_height(sim_x, sim_y) -> world Y`. Inside
the bowl it is

```
world_y = H_RIM - BOWL_DEPTH * profile(rho)
rho     = |P - BOWL_CENTRE| / BOWL_RADIUS
```

with `BOWL_CENTRE = (540, 1820)` and `BOWL_RADIUS = 470` exported from
`race/courses/neon.py` so the mesh and the mapping are built from one
description. That contract is sound and this lab does not dispute it.

---

## 2. Why the visual 3D bowl does not create real bowl physics

The mapping above is an honest presentation of a 2D simulation. The problem is
that the *simulation* underneath it is not a bowl, and no mapping can add
physics that was never computed. Five specific failures, in the order they
matter:

**2.1 The restoring force points one way, not inward.** On a real bowl the
in-surface force is the tangential projection of gravity,
`g_tan = g - (g . n) n`, and because the surface is a dish that projection
points radially *inward* from every direction on the rim. In the simulation
plane gravity is the constant vector `(0, +1500)`. A racer on the far side of
the disc (`sim_y < BOWL_CENTRE_Y`) is therefore accelerated toward the centre,
and a racer on the near side (`sim_y > BOWL_CENTRE_Y`) is accelerated *away*
from it, down and out. The bowl has a restoring force on one semicircle and an
expelling force on the other. That is not a bowl; it is a hill with a hole in
the middle of it, seen from above.

**2.2 There is no centripetal term.** A marble moving fast along a curved wall
generates a large normal force, and it is that force which bends its path
around the bowl. In the constrained equations the term is the quadratic form
`K = u_dot^T H u_dot` - the curvature of the surface times the square of the
speed. Nothing in a flat 2D space computes it. A racer's path between wall
contacts is a parabola in the plane, and the mapping redraws that parabola as a
descent. Wall-following is being simulated as a series of bounces off chords.

**2.3 Height and potential energy are different functions.** Simulation
potential energy is `m * GRAVITY * sim_y`. Presented height is
`H_RIM - BOWL_DEPTH * profile(rho)`. These are not the same function of
position and they are not even monotonically related: a racer that moves
*outward* along the `+x` axis gains presented height at zero simulated energy
cost, and one that moves inward along `-y` loses simulated potential energy
while gaining presented height. Energy is conserved in the plane and is not
conserved in the picture.

**2.4 Orbiting is therefore not available.** An orbit is a balance between a
centre-seeking force and a centripetal requirement. 2.1 says the first is
absent over half the disc and 2.2 says the second is never computed. What the
current bowl produces is a fall plus wall bounces, redrawn as a spiral by a
mapping in which "closer to the centre" happens to mean "lower".

**2.5 Collision responses are horizontal.** Two racers meeting are resolved by
a 2D impulse in the simulation plane. In the presented world those two marbles
may be on differently oriented parts of the dish, in which case the correct
response has a vertical component that nobody computed. The mapping then
reassigns each marble a new height from its new position, which is a
*teleport* in the presented world - small, but it is where the energy that
should have gone into the impact goes instead.

**Planned measurement.** Sections 2.1-2.4 predict something checkable on
production data: a racer crossing the neon bowl should accumulate very little
angular travel about `BOWL_CENTRE` before reaching the drain. The analysis will
run the same orbit metric defined in section 7 over the existing neon replay
and report revolutions per racer alongside the two prototypes. If the current
bowl is really a funnel, that number will be a small fraction of a turn.

---

## 3. Approach A - Python 2.5D surface physics

Python stays authoritative. The bowl is a mathematical surface of revolution
and a marble is a point constrained to it, in reduced coordinates.

**3.1 The chart.** A marble is two numbers, `(x, z)`, its horizontal position.
Its height is `y = f(x, z)`, evaluated, never integrated. This is the single
most important implementation decision in the prototype and it disposes of
three of the failure modes in section 23 of the brief for free: a marble cannot
sink below the surface, cannot hover above it and cannot drift off it, because
the constraint is not enforced - it is the coordinate system. Position error
against the surface is exactly zero at every tick, by construction.

**3.2 The surface.** `physics_lab/common/bowl.py`. A dish
`y = D (s/R)^p` with a drain lip: a circle of one marble radius, tangent to the
dish, that the marble rolls over on its way into the hole. Everything is stated
as the **centre surface** - where a marble's centre goes - and the collider a
3D engine needs is that surface offset by one radius along its inward normal
(`contact_profile`). Describing the centre and deriving the collider is what
makes a Bullet sphere at rest sit exactly where the Python constraint would put
it. Describing the collider and deriving the centre would leave the two bowls a
radius apart wherever the surface curves.

**3.3 The equations of motion.** For a surface `y = f(x, z)` with gravity
`-g y-hat`, Newton plus the constraint gives, in closed form,

```
lambda / m_eff = ( g / (1 + c)  +  K ) / ( 1 + |grad f|^2 )
x_ddot         = -f_x * lambda / m_eff
z_ddot         = -f_z * lambda / m_eff
K              = u_dot^T H u_dot
```

The horizontal acceleration is exactly the tangential projection of gravity
(the `K = 0` case is algebraically identical to `g - (g.n)n` projected into the
chart), plus the curvature term of 2.2. `lambda` is the normal force, and it is
a real number the prototype has rather than an assumption: the drain transition
in 3.5 is triggered by it reaching zero.

**3.4 Rolling.** A solid sphere rolling without slipping carries rotational
kinetic energy `(1/5) m v^2` alongside `(1/2) m v^2`, so the effective inertia
is `m_eff = (1 + c) m` with `c = 2/5`. In the constrained equations this is
algebraically identical to replacing `g` with `g / (1 + c) = (5/7) g`, which is
the familiar factor for a sphere rolling down a slope. It is included because
the true-3D prototype gets it automatically from friction, and without it the
two would differ by 40% in every acceleration.

The approximation being made, stated plainly: the contact point traces the
offset surface rather than the centre surface, so its speed differs from the
centre's by a factor of order `1 + r/R_curvature`, about 3% at the rim of this
bowl and less elsewhere; and gyroscopic terms from the spin axis reorienting as
the marble travels around the dish are neglected entirely. Both are documented
compromises, not oversights.

**3.5 The drain transition.** Not a teleport and not a radius test. The lip is
convex, so `K` goes sharply negative on it and `lambda` falls. When `lambda`
reaches zero the surface can no longer hold the marble and it is released into
a genuine 3D ballistic state - free position and velocity, still colliding with
other marbles - which falls down the drain shaft. A marble is counted as
drained when it passes `drain_exit_y`. A free marble whose centre comes back
below the surface re-contacts it with `surface_restitution`, so a marble thrown
up by a collision lands rather than falling through the world.

**3.6 Dissipation.** Two models, both physically interpretable, and the reason
there are two is section 5.3. `linear_damping` is a velocity-proportional decay
`dv/dt = -k v`. `rolling_resistance` is the honest model - a force
`mu_rr * |N|` opposing motion, using the normal force from 3.3 - and produces a
roughly constant deceleration instead. The comparable benchmark runs on
`linear_damping` because it is the model the 3D engine can be made to match;
`rolling_resistance` is swept separately and reported.

**3.7 Marble-marble collisions.** Done properly in 3D, then projected. Two
marbles touch when their world centres are within `2r`. The impulse is applied
along the 3D contact normal, and the response of a *constrained* marble to a 3D
impulse is `dV = T A^-1 T^T J`, where `T` maps chart velocity to world velocity
and `A = m_eff (I + grad f grad f^T)` is the reduced mass matrix. So the
effective inverse mass along the contact normal is `n^T T A^-1 T^T n`, which
correctly makes a marble hard to push into the hill and easy to push along it.
This is what section 14 of the brief asks for: a real 3D sphere-sphere impulse
whose result is re-projected onto each marble's own allowed tangent state, with
the projection falling out of the algebra rather than being applied afterwards.
Coulomb friction along the tangent and a positional split to remove overlap
complete it.

**3.8 Rotation.** `omega = (n x V) / r` for a rolling marble, integrated as a
quaternion, exported for the renderer. Secondary, and capped at that: it exists
so the videos can show whether marbles roll or skate, which is one of the
failure modes in section 23 and is invisible on an untextured sphere.

**3.9 Integrator.** Semi-implicit (symplectic) Euler in the chart, at a fixed
rate. Chosen over RK4 because collisions and state transitions have to be
handled between steps anyway, which destroys a high-order method's error
advantage, and because a symplectic method has bounded rather than growing
energy error. The rate is a measured choice: energy drift will be reported at
120, 240 and 480 Hz on a passive single-marble orbit and the benchmark rate set
from that. The initial figure in the configuration is 240 Hz.

---

## 4. Approach B - true 3D rigid-body physics

**4.1 Engine choice, and why it is not automatically Godot.** Three candidates
were assessed against what is actually installed:

| Candidate | Verdict |
| --- | --- |
| **PyBullet 3.2.7** | **Chosen as the primary.** Real 3D rigid bodies, fixed-step, headless, and it keeps Python authoritative - so if it wins, the entire existing pipeline survives unchanged. It has no cp313 Windows wheel and had to be compiled from the 76.8 MB source tarball against the MSVC 2022 build tools; that succeeded here, and the cost is reported rather than hidden. |
| **Godot 4.7.2 / Jolt** | **Run as a cross-check.** Already in the pipeline as the renderer, and `physics/3d/physics_engine = "Jolt Physics"` is selectable. But making it authoritative inverts the architecture - physics would live downstream of the replay it is supposed to produce - so it is measured to answer "what would we gain by moving physics into Godot", not assumed to be the answer. |
| **pymunk / Chipmunk** | Rejected. It is 2D. It is what production already uses and it is the thing under investigation. |

Running both is worth the extra work because they answer *different* questions.
PyBullet answers "can Python own 3D physics"; Godot answers "should the
authority move downstream". Section 31 of the brief asks for both and one
prototype cannot supply them.

**4.2 What is built.** The smallest possible benchmark, in both: a static
triangle mesh of the bowl collider from `contact_profile`, eight
`RigidBody`/`RigidBody3D` spheres at the run spec's exact starting states -
position, velocity *and* spin, so the 3D bodies are already rolling and do not
spend their first tenth of a second skidding while the 2.5D model does not -
gravity, and nothing else. No race, no course, no camera language, no
production scene. Godot's lives in its own project under `godot/physics_lab/`
so that nothing in `godot/project.godot` or the production scenes is touched.

**4.3 Stepping.** Fixed `1/physics_hz` steps, counted rather than timed. In
Godot that means counting `_physics_process` calls rather than reading a
clock, which makes the run independent of how fast the machine happens to be.

**4.4 Determinism investigation.** 20 identical runs of each seed, in-process
and across processes, compared on the raw-float digest described in
`common/labreplay.py` - not on the rounded JSON, which would answer a weaker
question. Where runs differ, report *when* they first differ, how position
divergence grows with time, and whether the drain order changes. No claim of
determinism will be made from a single similar-looking rerun.

---

## 5. Common benchmark definition

`physics_lab/common/bowl_benchmark.json` is the only place any of these numbers
is written down. Both prototypes read it; neither holds a constant.

| | value | why |
| --- | --- | --- |
| gravity | 9.81 m/s^2 | real units; a 3D engine is tuned around them |
| bowl rim radius | 0.50 m | a bowl a hand can hold, at toy-machine scale |
| bowl depth at rim | 0.18 m | rim slope 35.7 degrees - a wall, not a ramp |
| profile power | 2.0 | a paraboloid: analytic, and the canonical bowl |
| surface max radius | 0.60 m | past it, a marble has escaped and is reported |
| drain radius | 0.060 m | 3.0 marble diameters, ratio swept in section 8 |
| marble radius | 0.020 m | a 40 mm marble |
| marble mass | 0.0838 kg | that sphere in glass, density 2500 |
| restitution | 0.55 | marbles, damped |
| friction | 0.15 | marble on marble |
| linear damping | 0.15 /s | calibrated, see 5.3 |
| physics rate | 240 Hz | provisional; set by the drift measurement in 3.9 |
| sample rate | 60 fps | matches the production replay rate |
| duration limit | 30 s | past this the run is a failure and says so |
| seeds | 20 fixed | listed in the configuration |

**5.1 Initial conditions.** Eight marbles on the wall between 0.40 and 0.47 m,
evenly spaced in angle with up to 12 degrees of seeded jitter, each with a
prograde velocity between 0.78 and 1.14 of the *local circular-orbit speed*
plus a 12% inward radial component. Quoting speed as a fraction of orbit speed
is what makes "0.8" mean the same thing at every radius. All eight are
prograde: counter-rotating marbles would produce far more collisions, but they
would be head-on collisions a real machine fed from one chute never sees, and
they would flatter whichever engine handles violent impacts better.

**5.2 One generator, not two.** The initial conditions are generated once in
Python as an explicit `RunSpec` and handed to whichever engine is about to run,
including the ones that are not Python. Two engines each deriving conditions
from the same seed agree only until one of them consumes a random number the
other does not.

**5.3 Calibrated dissipation, and the honest problem with it.** The two
architectures do not expose the same dissipation model. The 2.5D prototype can
apply rolling resistance `mu_rr |N|`, which is what a marble actually
experiences. A rigid-body engine exposes `angular_damping`, which is
velocity-proportional, and for a rolling sphere it reaches the linear velocity
diluted by the rolling constraint - `dv/dt = -(2/7) d v`, not `-d v`. Setting
"the same number" in both would compare two different physical models.

So the coefficients are not matched; the *observable* is. A single-marble
passive orbit with no collisions is run in each engine and the damping tuned
until the orbital-energy half-life agrees within 2%. Everything else - orbits,
collisions, drain behaviour - is then compared on a level field. The calibrated
values are reported. This is a real methodological compromise and it is the
first thing a reader should be told about the comparison.

---

## 6. Common output format

Both prototypes write `physics_lab/common/labreplay.py` files: approach, seed,
rates, the benchmark, the run spec, 60 fps frames of
`(position, velocity, orientation, state)` per marble, and a typed event list -
collision, separated, landed, drained, escaped, failed. It is deliberately
**not** the production race replay schema; that one describes ranks,
checkpoints and course pieces, and widening it for an experiment that may be
discarded would be the wrong trade.

Each file carries a SHA-256 digest of the raw IEEE-754 bytes of every sampled
float, taken *before* rounding for storage. That is what the determinism work
compares.

---

## 7. Measurements

Per marble: entry speed, radius from centre over time, angular position and
angular velocity, **accumulated angular travel / 2 pi** (revolutions), speed
over time, mechanical energy proxy `m g y + (1/2)(1 + c) m |v|^2`, collision
count, time to drain, drain order.

Per run: total collisions, mean / min / max time to drain, all-drained time,
stuck marbles, escapes, stability failures, wall-clock cost.

Per approach: the above over all 20 seeds, plus the deterministic-repeat
result, the performance scaling at 8 / 16 / 32 / 64 marbles, and the failure
list from section 23 of the brief scanned for explicitly.

The revolutions metric is the headline. A marble that enters and heads straight
for the drain accumulates a small fraction of a turn; a marble that genuinely
orbits accumulates several. It is the one number that most directly separates
"a bowl" from "a funnel", and it is why section 2 predicts a value for the
current production bowl before this lab measures one.

---

## 8. Parameter sweeps

Physically interpretable parameters only, swept rather than tuned by eye:

* profile power 1.8 / 2.0 / 2.4 - how non-harmonic the dish is, which governs
  how much marbles mix
* linear damping 0.08 / 0.15 / 0.25 - orbit lifetime
* rolling resistance 0.010 / 0.020 / 0.030 - the alternative dissipation model
* drain diameter 2.0 / 2.5 / 3.0 / 4.0 marble diameters - throughput against
  arching and clogging
* restitution 0.35 / 0.55 / 0.75

The chosen values are reported with the measurement that chose them. No
hand-picked seed is allowed to decide anything: every sweep point is scored
over all 20 seeds.

---

## 9. Determinism test strategy

1. **In-process repeat.** Same spec, 20 runs, one process. Digests compared.
2. **Cross-process repeat.** Same spec, 20 separate process launches. This is
   the one that catches hash-ordering, address-dependent iteration order and
   uninitialised memory.
3. **Divergence profile.** Where digests differ, the first differing frame, and
   maximum position and velocity divergence as a function of time.
4. **Outcome stability.** Whether drain order and drain times differ across
   repeats, which is what actually matters for a seed search.
5. **Cross-machine.** Recorded as *not tested* unless a second machine is
   available. It will not be claimed on the basis of one machine.

The 2.5D prototype is expected to pass 1 and 2 trivially - it is pure Python
float arithmetic with no library state - and the interesting result is what the
rigid-body engines do.

---

## 10. Success and failure criteria

Fixed here, before any result exists.

**Physical believability** (all must hold, over all 20 seeds):

* median revolutions before drain >= 1.5, and >= 60% of marbles >= 1.0
* radius-vs-time regression slope negative for >= 80% of marbles
* with dissipation disabled, total mechanical energy drift over 10 s <= 1%
* with dissipation enabled, no frame-to-frame energy *increase* outside a
  collision tick
* zero escapes, zero NaN, zero tunnelling, no sustained overlap beyond 5% of a
  marble radius

**Throughput:** >= 90% of all marbles across all seeds drained inside 30 s;
no seed with more than one stuck marble.

**Determinism:** identical digests over 20 in-process and 20 cross-process
repeats, or a quantified account of exactly how and when they diverge.

**Speed:** a 20 s bowl simulated headless in <= 4 s at 8 marbles, which puts a
1000-seed search inside about an hour on one core.

**Verdict:** an approach that fails believability is out regardless of its
speed. An approach that passes believability but fails determinism is a
candidate only with a recorded-replay architecture. An approach that passes
both but cannot express the machine elements in section 30 of the brief - tube,
elevator, rotating gate, stacked track - is a bowl solution, not a machine
solution, and the report has to say so.

It is an acceptable outcome that neither approach passes.

---

## 11. Dependency implications

| | added | cost |
| --- | --- | --- |
| 2.5D | nothing | pure Python and the standard library |
| PyBullet | `pybullet` | no cp313 Windows wheel; 76.8 MB source build against MSVC 2022. Works, but it is a compiler dependency on every developer machine and in CI |
| Godot authority | nothing new | Godot is already required for rendering, but the *architecture* changes: physics would live downstream of the replay |

Nothing is installed into the production `.venv`. The lab has its own, and
`requirements.txt` on `race-v1` is untouched.

---

## 12. Order of work

1. this plan, the shared benchmark, the bowl geometry, and their tests
2. the 2.5D prototype, its invariant tests, its runner
3. the rigid-body prototypes and the determinism harness
4. metrics, plots, the neutral renderer, videos, and the comparison

Each is a commit on `race-physics-lab` and each is pushed.
