# Race V0.1 — obstacle-race prototype

Answers one question: **can ten balls racing through obstacles make an
entertaining, unpredictable 15–25 second simulation?**

Measured answer over 60 seeds: yes. Every race completed, the winner's time
landed between 14.96s and 19.31s, positions changed constantly (mean 4.7
lead changes, ~95 order swaps), and across those 60 races **all ten racers
won at least once**. No race had to be thrown away.

## A note on the engine

The brief specified Godot 4.7.2. This project's physics, rules, seeding and
replay export are all Python + pymunk; `godot/` is a Godot **4.2** project
that only renders exported replays, and says so in its own header. Building
the race in GDScript would have meant a second physics engine, a second
seeding scheme and a second replay format alongside the fight system rather
than beside it. So the race is Python, in the same shape as the duel, and
reuses the canvas, the geometry primitives, the seeded-stream convention and
the fixed-timestep clock the duel already uses.

## How to run

```bash
# watch a race (a window; 540x960 preview of the 1080x1920 frame)
python race_main.py
python race_main.py --seed 839271
python race_main.py --seed 839271 --debug        # overlay on from the start

# headless: no window, prints the summary
python race_main.py --headless --seed 839271

# PNG frames at given race times, no window (negative = during the countdown)
python race_main.py --seed 839271 --scale 0.5 \
    --snapshot docs/validation/race_v01/race \
    --snapshot-at=-2.2,3.0,7.5,11.0,15.0,17.0

# a batch, which is where the acceptance numbers come from
python -m tools.race_batch --count 20 --start-seed 1000
python -m tools.race_batch --seeds 839271,12345 --verbose
```

`--snapshot-at` needs the `=` form when the first value is negative,
otherwise argparse reads the leading `-` as an option.

The fight system is untouched and still runs exactly as before:
`python main.py --seed 12345`.

## Controls

| Key     | Action                                    |
| ------- | ----------------------------------------- |
| `R`     | Restart the current seed                  |
| `N`     | Generate a new seed and restart           |
| `Space` | Pause / resume                             |
| `F1`    | Toggle the debug overlay                  |
| `Esc`/`Q` | Quit                                    |

The debug overlay is **off by default** and draws nothing when off — there
is a test asserting the frame is pixel-identical with it disabled, so a
recording cannot pick it up by accident.

## Architecture

```
race/
├── config.py       every tunable number, in one place
├── seeds.py        three salted RNG streams: course, spawn, jitter
├── course.py       course as plain data (no pymunk, no rendering)
├── courses/
│   ├── builder.py  the scratch pad a course is assembled on
│   └── prototype.py the one V0.1 course, written top to bottom
├── racer.py        one competitor: body, identity, race state
├── runtime.py      course data -> pymunk bodies and shapes
├── simulation.py   the physics world; reports contacts, decides nothing
├── progress.py     checkpoint progress and ranking
├── manager.py      race rules: countdown, finishing, recovery
├── events.py       the ordered, tick-stamped record of what happened
├── telemetry.py    summary data and the printable block
└── camera.py       vertical camera for a 9:16 frame

rendering/race_renderer.py   pygame preview + HUD + debug overlay
race_main.py                 CLI
tools/race_batch.py          batch runner and aggregate report
```

The split mirrors the fight system deliberately: `engine.simulation` owns
physics and reports contacts, `modes.power_battle` owns the rules. Here
`race.simulation` owns physics and `race.manager` owns the rules.

**How a race runs.** `RaceSimulation` builds a pymunk space with gravity,
turns the `RaceCourse` into bodies via `TrackRuntime`, and places ten
`Racer`s on the grid. It steps at a fixed 120 Hz and reports what it saw —
racer-on-racer contacts, jump-pad kicks, spinner touches — as plain data.
It never decides anything.

`RaceManager` drives it. It holds the field behind the gate for a 3-second
countdown, removes the gate, and then each tick asks `progress.py` where
everyone is, records checkpoint crossings, finishes racers that cross the
finish plane, watches for stuck or escaped racers, and appends a
`RaceEvent` for every moment worth knowing about. `telemetry.py` reads the
finished race and reports it. `RaceCamera` and the renderer only ever read
state.

**Why ranking uses checkpoints.** The obvious approach — distance to the
finish — is wrong here. A racer that has fallen into the jump pit is lower
down the course than one still on the platform above it, but it is losing,
not winning. So progress is measured along a ladder of ten horizontal
checkpoint planes: which plane a racer has passed, plus how far it has got
towards the next. That is monotonic in the direction of travel by
construction, and there is a test asserting it over the whole course.

A checkpoint, once reached, stays reached, so a racer batted backwards by a
spinner keeps its credit; live progress is *not* a high-water mark, because
losing ground has to cost something.

**Seeding.** Three salted streams from one integer seed, following the
convention `engine.randomizer` set: `course` (spinner start angles and a few
per cent of speed variation), `spawn` (which racer gets which grid slot,
plus small offsets), `jitter` (jump-pad scatter, drawn while the race runs).
Separating them means adding a spinner cannot shift a racer's spawn, and one
extra pad kick cannot change the course. Jump kicks are applied in racer-id
order so the stream is consumed identically regardless of the order
Chipmunk happened to report contacts in.

There is no real-time accumulator anywhere. The preview steps exactly two
ticks per drawn frame, so a machine that cannot hold 60fps plays the race
*slowly* rather than playing a different race.

## The course

```
START         ten racers behind a gate, two rows of five
ACCELERATION  two steep slick shelves, each open at the opposite end
SPINNERS      an open shaft crossed by a 3-arm and a 4-arm rotor
FUNNEL        steep sides into a shallow basin draining through one hole
SCATTER       a peg triangle, breaking the single file back up
JUMP          slick run-up, kicker, and a gap with three outcomes
CHAOS         three plinko rows and one long 2-arm rotor
FINISH        a wide chute into a sloped paddock
```

Three things about this were only learned by measuring, and are worth not
re-learning:

**Shallow surfaces make a race empty, not gentle.** The first version spent
5.4s of a 16s race creeping down two 8-degree shelves and another 3.3s on a
flat catch ramp — over half the winner's time with nothing happening. Every
travelling surface is now steep enough to be over quickly, and the time
that bought went to the funnel and the jump.

**A V-funnel with a vertical throat does not congest.** It keeps the field
at full speed and ten racers shoot the gap nose to tail in about a second.
What congests is a *floor*: a shallow, ordinary-friction basin whose only
exit is a hole in the middle of it. Peak queue went from ~1 racer to 5.7.

**The funnel hole is sized by the arching threshold, not by taste.** At
100px against a 60px racer, two racers reliably wedge across it — one on
each lip, propped against each other — and the basin locks solid with the
whole field in it, in roughly one seed in twenty. At 126px that is
geometrically impossible, and measuring across 40 seeds showed congestion
is unchanged, because the queue comes from the friction of the approach.

## Physics notes

`MAX_SPEED` is the most consequential number in the race. Sweeping it from
1250 to 750 over 30 seeds moved the winner's mean from 14.6s to 16.8s and
lifted the *fastest* race of the batch from 12.9s to 15.2s — putting every
run inside the target band instead of most of them. It also raised funnel
congestion and evened out the three ways the jump can end, because a slower
field arrives closer together.

The cap is applied twice, and the second one is not obvious. A body's
`velocity_func` runs during integration, *before* the solver; a spinner arm
is an infinite-mass kinematic body, so resolving a deep contact against one
can hand a racer an enormous impulse afterwards. Measured over 40 seeds
that put racers up to **240% past the cap** — around 2500 px/s, a genuine
blur — for the tick before the hook next ran. So `RaceSimulation.step`
clamps again after the solver and after the pads. Overshoot is now exactly
zero, and the limit is identical for every racer, so it decides nothing
about who wins.

Two rules govern where a spinner can go: hubs further apart than the sum of
their reaches (two kinematic bodies pass *through* each other rather than
colliding), and every arm tip clearing the side wall by more than a racer's
diameter. A narrower gap than that is not a gap, it is a trap — a racer
driven into one gets batted against the wall by every passing arm and never
escapes. An earlier layout left 20px there and lost a racer to it in one
seed in fifteen. Both rules are asserted by tests.

## Recovery

Recovery is the only code in the race that moves a racer by hand. It lives
in one method, it is always logged as a `RaceEvent` and a telemetry count,
and it always costs the racer the ground it had covered since its last
checkpoint — usually a far heavier penalty than the recorded 1.5s.

A racer is stuck when it is *both* below 40 px/s and making no course
progress, continuously, for 3.5 seconds. Both conditions are required and
the window is long on purpose: a racer waiting its turn in the funnel basin
is barely moving and making no progress for seconds at a time, and it is
not stuck, it is racing. Anything shorter rescues racers out of the one
obstacle that is supposed to hold them up.

Leaving the course, or a position that stops being a number, is recovered
immediately with no waiting period. After four rescues a racer is retired
and removed from the space, so it cannot obstruct racers still racing. That
should be rare — it means the geometry beat the net — and it did not happen
once in 80 measured races.

Every respawn point is asserted clear of geometry and of every spinner
sweep, and asserted not to move a racer forwards.

## Test results

Real numbers from `python -m tools.race_batch`. Nothing here is estimated.

**60 seeds (2000–2059):**

```
Seeds tested: 60
Successful completions: 60
Full race failures: 0
Winner time: min 14.96s  mean 16.76s  max 19.31s
Winner time in 15-25s band: 59/60
Race duration: min 21.31s  mean 23.01s  max 25.81s
Racers finished: mean 8.00/10
Stuck racer recoveries: 5 (affecting 5 racers)
Retired racers: 0
Leader changes: mean 4.67  min 1  max 11
Overtakes: mean 94.5
Distinct winners: 10/10 racers
```

**20 seeds (1000–1019)** — the batch the brief asked for, saved as
`docs/validation/race_v01/batch20.json`:

```
Seeds tested: 20
Successful completions: 20
Full race failures: 0
Winner time: min 14.27s  mean 16.82s  max 18.36s
Winner time in 15-25s band: 18/20
Race duration: min 20.77s  mean 23.18s  max 24.86s
Racers finished: mean 8.70/10
Stuck racer recoveries: 2 (affecting 2 racers)
Retired racers: 0
Leader changes: mean 5.65  min 2  max 13
Distinct winners: 8/10 racers
```

**Unit tests:** 150 new race tests; full suite 907 passing, including all
757 pre-existing fight-system tests unchanged.

**Fight system regression:** `git status` shows only untracked new files —
no existing tracked file was modified. `main.py --seed 12345` produces an
identical result, fighters and frame count to the committed replay (the
only difference is the pre-existing replay format v4 → v6 gap, which adds a
per-frame `obstacles` key).

**Screenshots** in `docs/validation/race_v01/`: the grid behind the gate
mid-countdown, and the race at 3s, 7.5s, 11s, 15s and 17s, plus the debug
overlay at 9s.

## Known problems

- **Two of twenty seeds finish just under 15s** (14.27s, 14.96s). Within
  "approximately 15–25s" but at the edge. A small further cut to
  `MAX_SPEED` would fix it; I left it rather than re-tune on a 20-seed
  sample.
- **Not every racer finishes.** The race stops 6.5s after the winner, which
  brings 8–8.7 of 10 home on average. That is a deliberate trade (measured:
  a 3.5s grace gives 5.4/10, a 10s grace pushes the total past 25s), but it
  means the results table is usually incomplete. The unfinished racers are
  named in the summary as DNF, not hidden.
- **Overtakes ~95 per race is a high number** and somewhat sampling
  dependent (84 at 4 Hz, 103 at 24 Hz). It is a real measure of a
  high-churn race, not a bug, but it is not yet calibrated into anything
  meaningful.
- **No race replay export.** The duel writes a replay JSON that Godot
  renders; the race has nothing equivalent yet, so races can only be
  watched in the pygame preview or sampled as PNGs.
- **The HUD banner overlays the track.** Racers behind the top banner are
  partially hidden. Fine for a prototype, wrong for final framing.
- **Determinism is same-machine.** Chipmunk is deterministic for an
  identical sequence of operations on the same build; I have verified
  reproducibility on this machine and have not tested across platforms.
- **The spinner shaft has two unswept bands** (x < 110 and x > 946). A
  racer well out to one edge can fall past both rotors untouched. Not
  harmful, but the obstacle is less reliable than it looks.

## Next recommended work

Based on what the V0.1 results actually show, in priority order:

1. **Race replay export**, matching the duel's `replay/exporter.py`
   pattern. Everything downstream — Godot rendering, the QC and batch
   packaging already built for fights, candidate search over seeds — needs
   a replay file to exist. This is the biggest unlock and the race
   currently has no path into the existing production pipeline.
2. **Fix the finish grace trade** properly, rather than picking a
   compromise. Options worth testing: run to completion but cut the *clip*
   at the winner, or shorten the course tail so the field is tighter at the
   line.
3. **Nudge the duration floor** so no seed lands under 15s, on a 100+ seed
   sample rather than 20.
4. **A second course**, to prove `CourseBuilder` and the checkpoint ladder
   generalise before more obstacle types are added. The builder was written
   for this and has never been used twice.
5. **Then** the things V0.1 deliberately skipped: racer abilities, the
   cinematic camera director, trails and particles, interestingness
   scoring. All of them are cheaper once a race is a replay file.

I would not add obstacle types yet. Three is enough to show the race works,
and the funnel is the one that carries the drama — a fourth type is less
valuable than making the existing three reliable and recordable.
