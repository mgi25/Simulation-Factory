# Marble V1 — first true-3D integration

The first Simulation Factory clip where the machine is the authored premium
marble machine and the marbles move under real PyBullet physics. Godot draws;
it does not simulate.

    Python -> PyBullet (240 Hz) -> marble3d replay -> Godot -> frames -> mp4

Scope is deliberately three modules: **START -> BOWL -> S-CURVE**. No
collector, no split, no finish, no HUD, no audio.

## The clip

| | |
|---|---|
| video | `output/marble_v1/integration_v1.mp4` — 1080x1920, 60 fps, 8.80 s, no audio |
| seed | **7** |
| marbles | 8 |
| physics | 240 Hz, `DEFAULT_CONFIG` unchanged |
| replay | 528 frames at 60 fps |
| state digest | `e5fd4c65…` |

    python -m tools.marble3d_integrate --seed 7 --marbles 8 --name integration_v1 \
        --stills "start=8,bowl=150,drain=334,curve=430" \
        --stills-dir docs/validation/marble_v1

Seed 7 rather than a curated pick. It is the seed the physics core benchmarks
itself on, so its numbers are already in `docs/marble3d_physics_core.md` and it
is the determinism probe's default; using a different one here would mean two
reference runs to keep in mind. Across seeds 1, 7, 17 and 23 the run is 8.7 to
9.1 seconds with all eight marbles finishing, and 7 has the most
marble-on-marble contact of the four — 71 collisions, over 2.97 bowl
revolutions.

Timeline: release at 0.01 s, all eight in the bowl by 0.98 s, first drain at
5.84 s, last at 7.19 s, first finish 7.28 s, last 8.78 s.

## Branch

| | |
|---|---|
| branch | `marble-v1` |
| base | `5f9577d` — `visual-lab: lock premium hero art direction` |

The visual lab is the base rather than the physics core because it carries the
approved authored assets and sits on the newer `race-v1` lineage. The physics
core was brought in on top of it, commit by commit.

## What was imported, and why not a merge

`marble-physics-core` is **not** rooted on `race-v1`. Its first commit
`21cb907` has parent `53a9ee1`, the head of `race-physics-lab`. Merging the
branch would therefore have dragged the entire `physics_lab/` research lineage
into a production branch to obtain six commits that do not depend on it.

So the six production commits were cherry-picked in order with `-x`:

| origin | cherry-pick | subject |
|---|---|---|
| `21cb907` | `d2ccffd` | marble3d: establish production PyBullet world and units |
| `21c286b` | `848be85` | marble3d: add the module contract and a validated bowl |
| `75848b2` | `850f645` | marble3d: add modular start and curved track, joined by socket algebra |
| `7119d7f` | `0f2c4b1` | marble3d: add the fixed-step loop and a deterministic 3D replay |
| `7ca8372` | `b1604aa` | marble3d: harden the machine, benchmark it, and write down what it does |
| `8df266a` | `04e6da0` | docs: correct two run lengths in the marble3d rate table |

Every one applied without conflict. The imported tree is byte-identical to
`marble-physics-core` at `8df266a`:

    git diff 8df266a HEAD -- marble3d tools/marble3d_*.py docs/marble3d_physics_core.md   # empty

### Paths imported

    marble3d/                        the production package (21 modules)
    tools/marble3d_run.py            single run -> replay
    tools/marble3d_batch.py          seed sweeps
    tools/marble3d_validate.py       physics validation harness
    tools/marble3d_video.py          physics-core preview video
    tests/test_marble3d_*.py         9 files, 128 tests
    docs/marble3d_physics_core.md    the physics-core write-up
    docs/validation/marble3d/        hardening.json and three stills
    requirements.txt                 +1 line: pybullet>=3.2.7

### Refactoring required: none

`marble3d` proved genuinely self-contained. Nothing under `marble3d/`,
`tools/marble3d_*` or `tests/test_marble3d_*` imports `physics_lab`, `race`,
or any other research module — the only non-stdlib import in the package is
`pybullet`, and that is reached through `marble3d/world.py` alone. No research
code had to be lifted into production, and no import had to be rewritten.

The 128 imported tests pass unchanged on this branch.

## Coordinates

There is one conversion and it is the identity.

PyBullet is configured +Y up here, gravity -Y, the machine laid out in XZ, and
it is right-handed. Godot is +Y up and right-handed. Quaternions are `(x, y, z,
w)` in both. So positions, directions, linear velocities, angular velocities
and rotations all cross unchanged, and `PRESENTATION_SCALE` is 1.0 — one world
unit of physics is one metre of Godot, with a 1 wu marble in a 38 wu machine.

The conversion is written once, in `marble3d/presentation.py`, as five named
functions that happen to return their argument. They exist because the
alternative to one identity conversion is fifteen call sites that each decided
separately that none was needed, and a machine whose marbles orbit backwards is
noticed late. It is tested from both ends against the same golden vectors —
`tests/test_marble3d_presentation.py` and
`godot/scripts/marble3d_axis_check.gd`, whose output is committed at
`docs/validation/marble_v1/godot_axes.json`.

## The module contract

`marble3d/presentation.py` writes one document per run describing what the
machine *is*; `marble3d_scene.gd` reads it and builds the authored assets to
fit. Godot derives no geometry of its own and hard-codes no dimension.

Per module: id, type, origin, orientation, world bounds, entry and exit sockets
in world space, actuators with rest pose and travel, a `visual` block of
dimensions, and `anchors` — the few numbers a contact check needs. The bowl
additionally reports centre, up, rim radius, rim elevation, drain centre, drain
radius, shaft bottom and profile power.

| simulated | drawn | how it is fitted |
|---|---|---|
| `StartModule` | `start_platform` | swept along the chute's own collider frames |
| `BowlModule` | `hero_bowl` | re-parameterised: outer radius, power-law profile, drain |
| `CurveModule` | `s_curve` | swept along the exact centreline the collider was swept along |

### The assets are re-parameterised, not scaled

The visual lab authored its bowl at an inner radius of 2.52 with a marble of
0.30 — about eight marble-radii across. The physics bowl is 12.5 with a marble
of 0.5 — twenty-five. No single multiplier makes both the bowl and the marble
come out right. So the assets take their dimensions from the contract, and what
survives from the lab is the form language and the proportions that are
genuinely proportions, carried as ratios and re-applied at the physics
dimension.

The start needed more than that. The lab drew eight bays **side by side across
a deck**; the solver queues eight marbles **single file down a 21 wu incline**.
Those are different machines and no scale factor relates them, so
`start_platform.gd` gained a second build that draws a chute. Its channel is
built by `s_curve.gd` — the start channel and the track channel are the same
moulded part in the same machine — and its bays became gold studs on the wall
beside each marble, placed from `marble_starts()`, which is where the solver
puts them on tick zero.

The chute floor is swept along the contract's `centreline` rather than
reconstructed from `incline_deg`. The chute runs at one slope for most of its
length, flattens near the exit and blends between the two, so a straight ramp
at the mean angle would miss the floor by most of a marble at the exit — which
is the end the marbles leave from.

## Validation

`check_contact` (`marble3d/contact.py`) walks every running marble in every
frame against the geometry the contract implies, and now runs inside
`tools/marble3d_integrate.py` on every render, dry runs included. It reports
marbles below the drawn surface, marbles floating clear of it, marbles outside
the bowl shell and marbles off the channel.

On the delivered clip: **3765 marble samples over 528 frames, no findings.**

`check_against_replay` runs before that and compares the two documents; a
contract that disagrees with its replay raises rather than rendering.

Stills, all cut from the delivered render by the same command that made it:

    docs/validation/marble_v1/start.png          the queue held behind the gate
    docs/validation/marble_v1/bowl.png           orbiting, 2.5 s
    docs/validation/marble_v1/drain.png          spiralled in at the drain, 5.6 s
    docs/validation/marble_v1/curve.png          descending the S, 7.2 s
    docs/validation/marble_v1/contact_sheet.png  the four at one display height

## Godot does not simulate

There is no physics class in the render path. `marble3d_scene.gd` has no
`RigidBody3D`, no `PhysicsServer` call and no `stepSimulation`; `set_frame(i)`
is a pure function of the output frame index that looks the pose up in the
replay, and at the default 60 fps it is an exact lookup, so no marble is ever
drawn anywhere the solver did not put it. The gate is driven from the
contract's release schedule, not from a spline or a tween. Retired marbles keep
their last recorded pose.

The renderer hashes the replay and the contract before and after rendering and
refuses the result if either changed.

## Camera

Three shots, cut from the replay's own events. No director.

| shot | from | framing |
|---|---|---|
| start | frame 0 | the loaded queue and its gate, 35° at 16° up |
| bowl | frame 36 (0.60 s) | the whole dish, 35° at 30° up |
| curve | frame 338 (5.63 s) | the descent into the exit, 35° at 30° up |

The bowl is higher than the lab's 18° hero angle because at 18° the far rim
cuts across the running surface and the dish reads as a disc.

The curve's angle is the one number here that was measured rather than
inherited. The helix spirals directly under the dish that feeds it, so the bowl
is a ceiling over it: too flat and the near arc of the spiral hides the far one,
too steep and the bowl's outer flank fills the frame. Thirty degrees on this
framing puts the lens tucked under the bowl's overhang. It belongs to this bowl
over this curve — re-measure it for Track V2 rather than porting it.

## Known limitations

**The track design is a placeholder.** `marble-track-visual-lab` owns the final
Start, Bowl, Track and environment. What is here is the visual lab's form
language fitted to the solver's dimensions, for the purpose of proving the
integration. It is not an approved track design and should not be reviewed as
one.

**Bowl dissipation is timestep-dependent.** Bowl revolutions rise monotonically
with the physics rate — 2.08, 3.20, 5.01, 15.27 turns at 120, 240, 480, 960 Hz
— and never converge; at 1920 Hz marbles climb out of the dish.
`marble-physics-hardening` measured why: a marble on an analytic surface loses
nothing at any rate, but a marble on a *tessellated* one loses energy in
proportion to how often Bullet retires a contact against a new triangle, and
`contactBreakingThreshold` sets how much. It is not a physical effect and has no
continuum limit to converge on. **The rate is therefore not a parameter to reach
for, and Marble V1 stays at 240 Hz.** Nothing from that branch is merged here:
it is characterisation, off by default, and it recommends no production change.

**The environment is minimal.** Sky, fog and a six-lamp practical rig, at the
lab's art direction with its lengths scaled. Background depth beyond that is
the environment lab's job.

**Exposure is improved but not final.** The dish is the largest, palest,
flattest surface in the machine and it clipped to white. Three things came down
together: the pearl albedos from `marble-visual-polish` (`lab_palette.gd` only
— the rest of that branch is lab-scene work), the key rig, and the tonemap
exposure. It holds its profile now; it is not a graded image.

**Cross-machine determinism is unverified.** Same-seed runs are identical in
process and across fresh interpreters on this machine. No second machine was
available. See below for why this does not gate the pipeline.

## Determinism

    python -m tools.marble3d_determinism_probe --seed 7

Prints the state digest, event digest, drain order, frame count, physics rate,
a digest of every physics constant, and the Python, PyBullet, OS and
architecture that produced them — so two machines can be compared by diffing
eight lines.

On this machine (Windows 11, AMD64, Python 3.13.0, PyBullet API 202010061):

    state digest   e5fd4c658a703ab48e9331b362058189522ba8e6dc0e6f9698e9a68795bd13cf
    event digest   245ad6d0d9cbe6d24bf04b2b7f55e60505f124a0dc286ad0aa5772437db2f8b2
    drain order    [7, 0, 3, 6, 4, 1, 5, 2]
    physics        240 Hz  config 9e2996a538f315ef

Rendering does not depend on this. A seed is chosen on the machine that
simulates it, and what travels to the machine that renders it is the *replay*,
not the seed; Godot replays and never re-solves. So two computers disagreeing
about seed 7 cannot put a marble in the wrong place in a finished clip. What it
would change is the *numbers* — revolutions, drain order, finish spread — which
is why the probe exists.

## Replacing this with Track V2

The integration is built so the visual modules can be swapped without touching
the pipeline. Track V2 should need changes in exactly two places:

* **the module's `visual` block** in `marble3d/presentation.py`, if the new
  asset wants dimensions the current one does not report;
* **the asset's `build(palette, spec)`**, which is the only code that turns
  those numbers into meshes.

Not touched by a track swap: the PyBullet world, the machine and module
classes, the replay format, the coordinate conversion, `marble3d_scene.gd`'s
marble playback and actuator driving, `marble3d_render.gd`, the contact check,
or `tools/marble3d_integrate.py`.

Two things to re-measure rather than port: `CURVE_ELEVATION`, and the practical
lamp positions, which are placed off module anchors and will move with them.

If Track V2 changes the *collider* geometry as well as the visual — a different
bowl radius, a different curve sweep — then the module specs in
`marble3d/machines.py` change too, and the contract, the contact check and the
cameras all follow from them without further edits.
