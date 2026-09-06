# Marble V1 — first true-3D integration

The first Simulation Factory clip where the machine is the authored premium
marble machine and the marbles move under real PyBullet physics. Godot draws;
it does not simulate.

    Python -> PyBullet (240 Hz) -> marble3d replay -> Godot -> frames -> mp4

Scope is deliberately three modules: **START -> BOWL -> S-CURVE**. No
collector, no split, no finish, no HUD, no audio.

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
