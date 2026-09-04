# Race V0.2 — production bridge and a second course

Answers two questions.

**Can the race system use the production pipeline the fight system already
has?** Yes. A race exports a deterministic replay, Godot renders it to a
1080×1920 PNG sequence, and FFmpeg encodes that to an MP4 — through the same
tools, with no second pipeline. Measured: a rendered racer sits a **median
0.7 pixels** from where the replay says it is, and rendering one replay twice
gives byte-identical frames.

**Does the race architecture generalise past one course?** Yes, and it needed
one real change to do it. A second course was built that forks into two paths
and rejoins, which the V0.1 checkpoint ladder could not have ranked. Ranking
is now a route-aware progress graph. Over 50 seeds the fork splits the field
**47% / 53%** and the winner comes from the left path 27 times and the right
path 23.

The fight pipeline is provably unchanged: re-rendering a battle replay after
all of this produces frames **byte-identical** to the render made before it.

---

## How to run

```bash
# export a race replay (headless; no window, no display driver)
python race_main.py --seed 839271 --export-replay output/race_839271.json
python race_main.py --seed 1000 --course split --export-replay output/split_1000.json

# render it to a 1080x1920 PNG sequence through Godot
export GODOT_BIN=/path/to/Godot_v4.x
python tools/render_replay.py output/split_1000.json --output output/render_split_1000

# check the render is of the race the replay describes
python tools/verify_race_render.py output/render_split_1000 --frames 24

# encode to MP4 (races encode silent; there is no race soundtrack yet)
python tools/encode_short.py output/render_split_1000 --no-loudness

# batch numbers
python -m tools.race_batch --course split --count 50 --start-seed 1000
```

`--course` accepts `prototype` and `split` everywhere it appears.

---

## Part 1 — the race replay

`replay/race_exporter.py`, a sibling of `replay/exporter.py` rather than a
branch inside it. A fight frame is health and power; a race frame is rank,
checkpoint and finishing position. One function serving both would produce a
schema half of whose fields are null in either mode.

What the two **do** share is the contract — plain JSON, no timestamps, no
paths, no Python objects — and the reader's entry point into it:

```
mode == "race"      a race replay, schema v1
mode absent         a battle replay, schema v6
```

Every replay exported before race mode existed has no `mode` field, so
defaulting to `battle` keeps all of them valid. The two schemas are versioned
on independent counters because they describe different things and will grow
at different rates.

### Schema

```jsonc
// output/race_v02/split_1000.json, trimmed to one entry per list
{
  "version": 1, "mode": "race", "seed": 1000,
  "fps": 60, "physics_hz": 120, "ticks_per_frame": 2,
  "limit_seconds": 70.0,
  "canvas": {"width": 1080, "height": 1920},
  "course_id": "split",

  "course": {
    "id": "split", "width": 1080.0, "top": 0.0, "bottom": 6840.0,
    "height": 6840.0, "out_of_bounds_margin": 320.0,
    "metadata": {"branches": 2.0, "corridor_width": 480.0,
                 "drop": 6840.0, "playable_width": 1000.0},
    "sections": [{"name": "split", "top": 1290.0, "bottom": 4120.0}],
    "pieces": [{
      "id": 25, "type": "box", "role": "ramp", "material": "track",
      "section": "branch_left",
      "x": 335.0, "y": 1840.0, "radius": 0.0,
      "width": 464.004, "height": 26.0, "rotation_degrees": 142.883,
      "impulse": [0.0, 0.0], "impulse_jitter": 0.0
    }],
    "spinners": [{
      "id": 0, "x": 800.0, "y": 2480.0, "hub_radius": 40.0,
      "arm_count": 3, "arm_length": 128.0, "arm_thickness": 28.0,
      "angular_speed": 262.029, "start_angle": 113.661, "reach": 168.0,
      "material": "track", "section": "branch_right"
    }],
    "checkpoints": [{
      "index": 4, "name": "left_1", "y": 2010.0, "respawn": [95.0, 2030.0],
      "branch": "left", "x_min": null, "x_max": 540.0, "progress": 2.28
    }],
    "branches": ["left", "right"],
    "routes": [
      {"branch": "left",  "checkpoints": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 14, 15, 16]},
      {"branch": "right", "checkpoints": [0, 1, 2, 10, 11, 12, 13, 14, 15, 16]}
    ],
    "spawns": [{"slot": 0, "x": 160.0, "y": 500.0}],
    "finish": {"index": 16, "name": "finish", "y": 6540.0},
    "max_progress": 5.0
  },

  "camera": {
    "viewport_width": 1080.0, "viewport_height": 1920.0,
    "lead_fraction": 0.42, "focus_group": 3, "follow_rate": 6.0
  },

  "racers": [{
    "id": 0, "name": "Racer_01", "color": [235, 72, 72],
    "radius": 30.0, "spawn_slot": 7, "contestant_type": "ball"
  }],

  "frames": [{
    "tick": 1200, "race_time": 7.0,
    "camera_y": 3002.631,
    "gates_open": true,
    "racers": [{
      "id": 0, "x": 978.73, "y": 3389.681, "rotation_degrees": 190.359,
      "vx": 539.656, "vy": 520.837, "speed": 750.0,
      "rank": 7, "checkpoint": 11, "branch": "right", "progress": 2.677,
      "finished": false, "retired": false, "recoveries": 0
    }],
    "spinners": [{"id": 0, "x": 800.0, "y": 2480.0, "rotation_degrees": 213.946}]
  }],

  "events": [{
    "tick": 545, "race_time": 1.542, "type": "checkpoint",
    "racer_id": 2, "x": 1010.1, "y": 1621.456,
    "value": 2.15, "detail": "right_entry"
  }],

  "result": {
    "winner_id": 2, "winner_name": "Racer_03", "winner_time": 12.275,
    "finished_tick": 2272, "duration": 15.933, "timed_out": false,
    "state": "complete",
    "finish_order": [{
      "position": 1, "racer_id": 2, "name": "Racer_03", "finish_tick": 1833,
      "finish_time": 12.275, "time_penalty": 0.0, "official_time": 12.275
    }],
    "racers_finished": 10, "leader_changes": 5, "overtakes": 96,
    "large_collisions": 13, "recoveries": 0, "retirements": 0,
    "spinner_contacts": 11
  }
}
```

### Three decisions worth knowing about

**Course geometry is exported in full.** A renderer rebuilds the exact course
from the replay alone and never imports a course builder — the same argument
the duel's arena layout is exported under. Two sources of truth for geometry
means that the day they disagree, the replay is the one that is wrong.

**Spinner transforms are exported per frame.** The spec describes the motion;
the renderer never evaluates it. It is handed where each arm actually was,
which is what keeps playback correct the day a spinner can be stalled,
blocked or stopped by something a formula does not know about.

**The camera track is exported per frame.** The camera is presentation, but
it is *derived* presentation — it follows the leading group, so reproducing
it in the renderer would mean reproducing ranking too. `camera_y` is the
course height at the top of the frame, advanced by exactly the same fixed
step the live preview uses. A test asserts the recorded track equals a live
preview's, element for element.

Velocity (`vx`, `vy`, `speed`) is exported although nothing reads it yet: it
is the state a renderer cannot recover without differentiating positions
across frames, and it is what trails, impact intensity and motion blur will
be driven from. Three numbers a frame is cheap against re-exporting later.

A race replay runs 2.5–3.5 MiB for a 17–26 second race — ten racers at
thirteen fields against a duel's two fighters.

---

## Part 2 — the production pipeline

```
Race Simulation          race/simulation.py + race/manager.py
        |                120 Hz fixed step, seeded, no wall clock
        v
     Replay              replay/race_exporter.py
        |                sampled at 60 Hz; course, camera, spinners, events
        v
      Godot              tools/render_replay.py -> godot/scripts/offline_render.gd
        |                one output frame per drawn frame, clock = frame index
        v
     Frames              output/<render>/frames/frame_000000.png ...
        |                1080x1920 PNG, counted, measured and sampled before acceptance
        v
      Video              tools/encode_short.py -> rendering/encode.py -> FFmpeg
                         H.264 High, yuv420p, 60 fps CFR, silent for races
```

Nothing in that chain is new except the exporter and the Godot race scene.
The stages between them were made **mode-aware rather than duplicated**:

| stage | change |
|---|---|
| `rendering/render_plan.py` | reads `mode`, carries it into the plan and the sidecar. `RENDER_FORMAT_VERSION` stays at 1 — the field was added, nothing replaced, so existing renders still pass QC |
| `tools/render_replay.py` | validates each mode against its own schema version; the Godot command is unchanged and mentions no mode at all |
| `godot/scripts/replay_viewer.gd` | dispatches on `mode`; a battle is built and played exactly as before, a race is handed to `race_scene.gd` |
| `rendering/encode.py` | `audio=None` produces a video-only MP4; `probe_problems(expect_audio=False)` *inverts* the audio checks rather than dropping them |
| `tools/encode_short.py` | races encode silent by default (`--force-audio` overrides, `--silent` forces it for either mode) |

Races encode silent because the soundtrack in `audio/` is written for a duel
— its cues are hits, powers and eliminations. Muxing a silent WAV so the
command shape never changed would put a stream in the file that claims to be
audio and is not. A file with no audio track says what it is.

### The Godot race scene

`godot/scripts/race_scene.gd` builds the course from the replay's geometry and
animates it from the replay's frames. Nothing about the race is computed
there. Two things make it a separate scene rather than a branch per function:

* **The camera travels.** A course is 6 800 pixels tall against a 1 920 pixel
  frame. It reads `camera_y` and does no following of its own.
* **It is orthographic and points straight down**, where the duel's camera is
  a 78° perspective one. That is a V0.2 decision rather than a style: it maps
  one simulation pixel to one frame pixel everywhere in the frame, so a
  rendered frame can be checked against the replay position by position. It
  also flattens the picture, which is a known cost — see *Known issues*.

`godot/scripts/race_hud.gd` is a small overlay: the clock, the top three by
the rank the simulation assigned, the countdown numeral and the result panel.
Rank is read, never recomputed — on a branching course two racers at the same
height are not level, and that judgement belongs in one place.

### Rendering test — 3 seeds

`tools/verify_race_render.py` takes each racer's recorded position, converts
it to a frame pixel (`x`, `y - camera_y` — no projection to invert), collects
the nearby pixels whose colour points the same way as that racer's, and
measures the box they fill.

| render | frames | positions | located | mean | median | 95th | worst |
|---|---|---|---|---|---|---|---|
| `prototype` seed 839271 | 20 | 149 | 149 | 1.50 px | 0.73 px | 8.43 px | 13.52 px |
| `split` seed 1000 | 24 | 189 | 189 | 1.00 px | 0.68 px | 4.86 px | 8.41 px |
| `split` seed 1007 | 20 | 154 | 154 | 1.51 px | 0.68 px | 7.53 px | 10.32 px |

Measured silhouettes average 1.01–1.02× the diameter the replay states.

**Determinism:** `split` seed 1000 rendered twice, 33 frames sampled across
1 245, **33/33 byte-identical**.

**Fight-mode regression:** `output/batch_audit10/replays/003_seed_21465.json`
(a v6 battle replay with no `mode` field) re-rendered after every change in
this phase, compared against the render made before it: **18/18 sampled
frames byte-identical**.

### Unavoidable rendering differences

The residual few pixels in the table above are properties of the measurement,
not of the renderer, and all three are documented in the tool:

* **Glow.** Godot bleeds a halo around a lit ball in exactly the racer's hue,
  so no colour test can reject it; a brightness floor holds most of it out and
  the silhouette can still measure up to 1.55× on the brightest racers.
* **Occlusion.** A racer resting against a wall, or buried in the pile of
  finished racers in the paddock, has part of itself hidden — it measures
  smaller and its box shifts away from what is covered.
* **The silver racer.** Racer 09's hue is the closest of the ten to the slate
  course chrome. Its worst case — silver, against a slate wall, inside the
  finish pile — is the 13.52 px outlier in the prototype row. Every other
  measurement on that render is under 3 px.

The overlay is drawn on top of the race, so racers behind the clock, the
standings or the result panel are skipped rather than measured.

---

## Part 3 — the split course

`race/courses/split.py`, 6 840 pixels deep.

```
START            ten racers behind a gate
OPENING          four rows of pegs across the full width
SPLIT            a wall down the middle, capped by a peg
 |          \
LEFT         RIGHT
switchback   steep slick chutes through one pass
of six       with a rotor turning under it
shelves
 |          /
REJOIN           a wide merge, 280px, no throat
FINAL            plinko, a rotor, a scatter, a second rotor
FINISH           a wide chute into a sloped paddock
```

### How it differs structurally from the prototype

|  | prototype | split |
|---|---|---|
| shape | a ladder — every racer meets every obstacle in the same order | a fork — two paths over the same stretch of canvas |
| progress | 10 planes, 0…9, one per rung | 6 main-line planes plus 11 branch nodes on two routes |
| ranking key | position on one ladder | position on the route the racer is actually on |
| congestion | a funnel basin draining through one hole | none — the branches carry the field instead |
| what decides the race | the funnel and the jump | which side of the splitter a racer comes off, and the pass |

It is **not** a rearrangement of the same vertical sequence. The prototype's
defining assumption — that "further along" and "further down" mean the same
thing — is false here by construction.

### Nothing chooses a branch

There is no rule, no die roll and no per-racer preference anywhere in the
file. There is a peg on the centre line with a wall beneath it: a racer left
of it falls into the left corridor and a racer right of it falls into the
right one. That is the whole mechanism.

Getting it to work took three attempts, and the two failures are the useful
part:

1. **Two slick shelves as the opening.** A shelf *translates* a field —
   every racer that lands on one leaves it at the same place. Measured at the
   splitter, all ten racers arrived within 14 pixels of each other, hard
   against the left wall. Every racer in every seed went left.
2. **A V and a throat feeding the peg.** This fixed the mean and destroyed the
   variance: the throat released racers one at a time on the same line, the
   peg deflected them all the same way, and every racer in every seed went
   right.
3. **Four rows of pegs across the full width, and nothing else.** Pegs do not
   translate a field, they spread one. Measured at the split plane: x from 70
   to 1011, mean 543, standard deviation 377. The fork works.

### Balancing the two paths

The right-hand branch is a steep slick run through a floor with one hole in
it and a rotor turning directly beneath — so every racer on that side goes
through the same gap and meets an arm on the way out. The hazard cannot be
avoided by taking a good line, only survived or not.

The left-hand branch is six grippy shelves with nothing on them at all.

The slope of those shelves is the number that decides whether the course has
a fork, and it was found by measurement:

| left shelf slope | left split→rejoin | right split→rejoin | winners L/R (16 seeds) |
|---|---|---|---|
| 14° (first version) | 9.28 s [8.7–10.3] | 6.72 s [6.0–8.2] | 0 / 16 |
| 31° | 7.14 s [6.8–7.7] | 6.66 s [6.0–8.0] | 5 / 11 |
| **37° (shipped)** | **6.71 s [6.5–7.3]** | **6.67 s [6.0–8.0]** | **9 / 7** |
| 42° | 6.54 s [6.3–7.1] | 6.67 s [6.0–8.0] | 4 / 12 |

The two are not level because the numbers were matched. They are level
because the **distributions overlap**: the left runs 6.5–7.3 s and almost
never anything else, the right runs 6.0–8.0 s depending entirely on the
rotor. A clean run down the right beats any run down the left, and a caught
one loses to all of them.

Two other numbers were found by failure and are worth recording:

* The right branch's first chute originally ended 60 pixels from the wall —
  exactly one racer diameter. **The whole field wedged there in every seed**
  and all ten racers were retired. Every open end on the course now leaves at
  least 100 px against a 60 px racer.
* The split checkpoint's respawn point sat 14 pixels **inside** the splitter
  peg. A rescued racer would have been rescued into a wall, failed to move,
  and been retired four seconds later having done nothing wrong. There is now
  a test that measures the true distance from every respawn point on every
  course to every piece and every spinner.

---

## Ranking across branches

The V0.1 ladder ranked by which horizontal plane a racer had passed and how
far it had got towards the next. On a fork that is wrong: two racers at the
same height are not necessarily level, because one may be four nodes into a
long detour while the other is two into a short chute.

### The design

A course is a **progress graph**. Each `Checkpoint` gained three fields, all
inert on a linear course:

```python
branch:   str          # "" is the shared main line; anything else is a path
x_min/x_max: float|None  # the corridor - mandatory on a branch node
progress: float        # course progress at this plane; what ranking compares
```

`progress` — not `y`, not `index` — is the ranking key. On a linear course it
defaults to the node's position in the ladder, which is why the prototype
behaves exactly as it always did. On the split course the main line is
numbered 0…5 and the two paths carry values inside the interval `(2, 3)`:

```
              split 2.0
             /          \
  left_entry 2.15        right_entry 2.15
  left_1     2.28        right_1     2.42
  left_2     2.40        right_2     2.70
  left_3     2.51        right_exit  2.88
  left_4     2.62             |
  left_5     2.72             |
  left_exit  2.88             |
             \          /
              rejoin 3.0
```

Both paths **enter at one value and leave at one value**, because two racers
taking different paths have to start and end the split level. What separates
them is how long each path took, not which one it was.

### The rule, in four steps

1. A racer's candidate nodes are those with `progress` above its own mark
   *and* on a route it may still take — the main line always, its own branch
   if it has one, any branch if it has not.
2. A node is reached when the racer is at or below its plane **and** inside
   its corridor. Corridors are what physically separate the paths.
3. Reaching a branch node commits the racer to that branch. Reaching a
   main-line node clears it — a main-line node is on every route, so crossing
   one means the split is behind. That makes multiple sequential splits work
   with no extra machinery.
4. Continuous progress interpolates between the last node reached and the
   next node **on that racer's route**, by height between those two planes.

Height is still what interpolates *within* a pair of nodes — that is correct,
because within one branch the racer is going downhill. What is no longer
true is that height alone decides the answer: the mapping from height to
progress is different on each path, and that is the entire point.

The course validates the invariants the rule depends on: unique names,
strictly increasing progress and height along every route, a corridor on
every branch node, exactly one finish on the main line, nodes at equal
progress sharing a plane, and branches leaving the same point starting at the
same value.

### Why not the alternatives

* **Y-position** — the failure this replaces.
* **Distance to the finish** — ranks a racer that has fallen into a pit ahead
  of one on the platform above it.
* **A per-branch scale factor** — needs someone to decide what a branch is
  worth. The graph asks how far through a path a racer is, which is a fact.

### Cost to the linear path

None measurable. All 20 stored V0.1 validation seeds reproduce **bit-for-bit
identically** after the refactor — same winner, same times, same lead
changes, same recovery counts, every field of every summary.

---

## Test results

Full suite: **977 passed** (907 before this phase).

New: `tests/test_race_replay.py` (27), `tests/test_race_branching.py` (29),
`tests/test_race_pipeline.py` (14).

### Batch: 50 seeds per course, seeds 1000–1049

| | prototype | split |
|---|---|---|
| successful completions | **50 / 50** | **50 / 50** |
| failures | 0 | 0 |
| winner time | 14.27 / **16.74** / 18.36 s | 11.91 / **12.53** / 13.36 s |
| in the 15–25 s band | 48 / 50 | **0 / 50** |
| race duration | 20.77 / **23.02** / 24.86 s | 15.12 / **16.94** / 19.24 s |
| mean finishers | 8.48 / 10 | **9.92 / 10** |
| recoveries | 3 (3 racers) | **0** |
| retirements | **0** | **0** |
| lead changes | 4.98 mean (1–13) | 4.90 mean (1–9) |
| overtakes | 94.1 mean | 86.5 mean |
| large collisions | 30.5 mean | 16.6 mean |
| spinner contacts | 25.3 mean | 13.7 mean |
| distinct winners | **10 / 10** | **10 / 10** |
| branch entries | n/a | left 237 (47%) · right 263 (53%) |
| branch winners | n/a | left 27 · right 23 |

Raw summaries: `docs/validation/race_v02/prototype50.json`,
`docs/validation/race_v02/split50.json`.

The prototype numbers are unchanged from V0.1 within the different seed
range, which is the point of quoting them.

---

## Compatibility

* **Fight mode is byte-identical.** A v6 battle replay with no `mode` field,
  re-rendered after every change here, produced frames byte-identical to the
  render made before this phase (18/18 sampled).
* `replay/exporter.py` is **untouched**. Battle replays still carry no `mode`
  field; readers default to battle.
* `RENDER_FORMAT_VERSION` stays at 1. `replay.mode` was added to the sidecar
  and nothing was replaced, so existing renders still pass production QC.
* `encode_command` with an audio path produces exactly the argument list it
  always did — a test asserts it flag by flag.
* All 907 pre-existing tests still pass, unmodified apart from one line in
  `test_render_plan.py` that pins the sidecar's `replay` block and now
  includes `"mode": "battle"`.
* All 20 stored V0.1 race validation seeds reproduce bit-for-bit.

---

## Known issues

1. **The split course finishes in 12.5 s, below the 15–25 s content band.**
   0 of 50 seeds land in it. The course is reliable and the fork is balanced;
   it is simply quick. Lengthening it means either deepening the run-in after
   the merge again or re-tuning the branch balance, and the balance was
   expensive to find. This is the one acceptance target this phase misses.

2. **The race renders flat.** The orthographic straight-down camera was
   chosen so a frame could be checked against the replay pixel for pixel, and
   it costs all the depth the battle renderer has. Correct playback was the
   V0.2 goal; this is the first thing a visual phase should revisit.

3. **Races do not go through `produce_batch` / QC / delivery.** Those stages
   are built around battle curation — powers, candidate scoring, a manifest
   of selected battles — and none of that exists for races yet. The chain
   that does work end to end is replay → render → verify → encode.

4. **No race soundtrack.** `audio/` synthesises cues for a duel. Races encode
   silent; `--force-audio` will run the battle soundtrack against a race
   replay and produce something meaningless.

5. **The prototype leaves 1.5 racers unfinished on average** (8.48 of 10).
   Unchanged from V0.1 — the finish grace window is 6.5 s and the funnel
   spreads the field further than that. The split course does not have this
   problem (9.92 of 10).

6. **`verify_race_render.py` cannot measure the silver racer reliably.** Its
   hue is close to the course chrome. The tool reports the whole distribution
   rather than a pass/fail so this is visible rather than hidden, but a
   distinct colour would be better than a wide tolerance.

7. **Branch usage is read back out of the event log**, because a racer's
   branch is cleared the moment its route rejoins the main line. That is
   correct for ranking and means telemetry has to reconstruct it. If more
   analysis needs it, the racer should keep a list of branches travelled.

---

## Recommended next work

**Do not start V0.3 on this list without deciding which of the three
directions matters.** The architecture question V0.2 was built to answer is
answered; what to spend the next phase on is a product decision.

In order of what the results actually argue for:

1. **Visual phase for races.** This is the clear first candidate. The system
   is production-correct and looks like a debug view. The orthographic camera
   was a deliberate scaffold and has served its purpose — a perspective
   camera, real materials, trails driven by the velocity already in the
   replay, and impact effects driven by the events already in the replay.
   Nothing new needs exporting.

2. **Course length and pacing.** The split course is 2.5 s short of the
   content band and the prototype loses 1.5 racers a race. Both are tuning
   problems with measurable targets, and both are cheap next to anything
   structural.

3. **A third course, before the procedural generator.** Two courses proved
   the abstraction handles a fork. A third — a loop, a course with a hazard
   that removes racers, or one with three paths — would find the next thing
   the abstraction cannot do, and it is much cheaper to find that now than
   inside a generator. The obvious candidates the current model does *not*
   support: a route that is not monotonic in `y`, and contestants that are
   not circles.

4. **Race curation.** `evaluation/` scores battles. Nothing scores races, so
   there is no way to pick a good one out of fifty. This is what stands
   between "the pipeline works" and "the pipeline produces content", but it
   depends on knowing what makes a race worth watching — which the telemetry
   now collects and nobody has looked at yet.

Explicitly *not* recommended yet: the procedural generator, alternate
contestant shapes, the cinematic camera director, and dynamic music. Each of
them is easier after the visual phase, and the generator is much easier after
a third hand-built course.

---

## Files

**New**

```
replay/race_exporter.py          race replay export
race/courses/split.py            the branching course
godot/scripts/race_scene.gd      race playback
godot/scripts/race_hud.gd        race overlay
tools/verify_race_render.py      render vs replay verification
tests/test_race_replay.py
tests/test_race_branching.py
tests/test_race_pipeline.py
docs/race_v02.md
docs/validation/race_v02/prototype50.json
docs/validation/race_v02/split50.json
```

**Modified**

```
race/course.py                   branch/corridor/progress on Checkpoint; the graph
race/progress.py                 route-aware progress; branch commitment
race/racer.py                    Racer.branch
race/manager.py                  finish by node identity; reset_progress
race/telemetry.py                branch_usage; max_progress in the display
race/courses/builder.py          branch_checkpoint; main-line stage counter
race/courses/__init__.py         split registered
race_main.py                     --export-replay
rendering/render_plan.py         mode in the plan and the sidecar
rendering/encode.py              audio=None; expect_audio
rendering/race_renderer.py       branch planes drawn to their corridor
tools/render_replay.py           per-mode schema versions
tools/encode_short.py            --silent, --force-audio; races silent by default
tools/race_batch.py              branch entry and winner reporting
godot/scripts/replay_viewer.gd   mode dispatch
tests/test_render_plan.py        the sidecar's replay block now carries mode
```
