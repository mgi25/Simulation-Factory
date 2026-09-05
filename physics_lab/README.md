# physics_lab

An isolated research lab. Nothing in here is production, nothing in here is
imported by production, and nothing in here may be merged into `race-v1` or
`main` without an explicit instruction to do so.

It exists to answer one question with measurements instead of opinion:

> Can we achieve convincing marble-machine physics while keeping Python
> authoritative, or should this project move to true 3D rigid-body physics?

Read [`EXPERIMENT_PLAN.md`](EXPERIMENT_PLAN.md) first. It was written before
any prototype existed and it fixes the benchmark, the measurements and the
pass/fail criteria, so that the criteria cannot be adjusted to fit whichever
result arrived. The finished comparison is
[`docs/physics_lab_bowl_comparison.md`](../docs/physics_lab_bowl_comparison.md).

## Layout

```
common/       the benchmark: one JSON configuration, the bowl geometry,
              the initial-condition generator, the lab time-series format
surface25d/   approach A - Python authoritative, marble constrained to a
              mathematical surface in reduced coordinates
rigid3d/      approach B - true 3D rigid bodies, in PyBullet (primary) and
              in Godot/Jolt (cross-check)
analysis/     metrics, plots and the neutral renderer both approaches are
              drawn by, so that a comparison is about the physics
```

with entry points in `tools/physics_lab_*.py` and tests in
`tests/test_physics_lab_*.py`. The Godot cross-check has its own self-contained
project in `godot/physics_lab/`, deliberately separate from `godot/` so that no
production scene, material or project setting is touched by this work.

## Running it

The lab has its own virtual environment, because PyBullet is not a production
dependency and must not become one by accident. From the worktree root:

```
python -m venv .venv
.venv/Scripts/python -m pip install pymunk pygame pytest pybullet
```

On Windows with Python 3.13 there is no PyBullet wheel and pip will build the
76.8 MB source tarball against the MSVC build tools. It works; it takes a
while. That cost is part of the finding, not an obstacle to it.

Then:

```
.venv/Scripts/python tools/physics_lab_bench.py --help
```

## The one thing to know before reading the code

Everything is described in terms of the **centre surface** - the surface a
marble's *centre* travels on - and never the collider. A sphere resting on a
collider has its centre one radius off it along the normal, and that offset
grows wherever the surface curves. Describe the centre surface, hand the 3D
engines the offset of it, and a Bullet sphere at rest sits exactly where the
Python constraint would have put it. Describe the collider instead and the two
experiments are quietly comparing two different bowls.
