# V1.4, part one: the line-to-radial start

**Status: built, geometrically validated, and traced in simulation to three
named stall sites. Not production-viable and not fairness-benchmarked.**
Throughput is 41.7% of the field (20 of 48 racers over six seeds of the start
lab). The shipped V1.3 course is untouched - `sloped.course.START_KIND` is
still `"fan"`, `sloped_course()` builds the same thirteen modules, and nothing
in this document changes a number in `docs/sloped_race_v13.md`.

This is a report of where the architecture actually stands, not of an intention.

---

## 1. Why the topology changed, and what was built

`docs/sloped_race_convergence_constraint` and `docs/sloped_race_v13_basin.md`
measured one mechanism in two topologies:

> a single common exit orders the field by distance to that exit, and distance
> to the exit is a function of which bay a marble started in.

Twenty-four geometries inside the taper/basin family have been falsified. The
brief's answer - and the memory note's - is to arrange the launch points *about*
the exit rather than beside it. `sloped/radial.py` builds that:

    visible 8-bay shelf, flat, one synchronised gate    <- unchanged, and seen
      |  the same shelf, fanning: 0.63 pitch eased to 1.20
    eight walled chutes, hidden under the platform
      |
    eight identical cups on one circle about the drain  <- the fairness surface
      |  one synchronised port release at 3.40 s
    a conical dish, eight-fold symmetric, eight vanes, central drain
      |
    a chute onto the launch run

**The cups are the design.** Each is the same short pocket at the same radius
from the drain, on the same level, closed by the same paddle, and all eight
paddles lift together. Distance from bay to exit is then *identical* for all
eight bays - the measured mechanism removed at its root rather than diluted.
Section 7 of the brief permits exactly this global mechanism; nothing is
per-marble.

### The exact slot map falls out of a linear map

Take the lip parameter `v = (i - 3.5) / 3.5` and send it to ring angle
`270 + 157.5 v` degrees. Because `157.5 / 3.5 = 45`, the eight bays land on
22.5 + 45k *exactly*, with the outer bays on the far cups and the inner bays on
the near ones - which is the nesting order that keeps the chute routes from
crossing. The first build had it backwards and every route had to cut across the
ones outside it.

---

## 2. What the geometry check proves, and what it flags

`tools/sloped_radial_check.py`, run before any marble:

| | |
|---|---|
| drop spread, bay to bay | **0.000000** |
| port radius spread | **0.000000** |
| port angles | 22.5 + 45k, exact |
| chute length spread | 5.74 (2.6 to 8.3) |
| mesh | 5740 vertices, 8006 triangles, **0 findings** |
| chute floor over the dish rim | +0.06 |
| chute floor over a foreign cup | +0.005 |
| worst chute pair isolation | 0.58 plan / 0.29 rise against 0.92 / 0.48 |

So the two properties fairness rests on - **equal drop and equal port radius** -
are exact, and the mesh is clean. The chutes are *not* congruent and cannot be:
eight collinear mouths cannot be mapped onto eight points of a circle by
congruent curves, and forcing equal length with detours only trades a length
difference for a curvature difference. That is what the cups exist to absorb.

---

## 3. The feasibility wall, stated plainly

Eight hidden chutes have to satisfy three constraints at once:

1. **≥ ~10° everywhere**, or a marble stalls. The basin measured 0.9° moving
   nothing and 7.9° working.
2. **≤ ~45° everywhere**, or the chute is a fall onto a paddle rather than a
   delivery.
3. **≥ 0.92 apart in plan or ≥ 0.48 in height**, or one chute's wall foot
   stands inside its neighbour's clear channel.

In the plan available - about two units between the fan's lip and the ring -
these are mutually infeasible, and the reason is structural: the wrapping
chutes are long (so shallow) and the near chutes are short (so steep), because
one has to travel 140° round the ring and the other 12°. Six configurations were
measured:

* per-chute **descent profiles** to separate the crossings in height: a profile
  shallow enough to hold a chute high through a crossing is shallower than the
  stall threshold. Falsified.
* **widening the fan** to 1.20 pitch and pushing the wrapping routes to radius
  3.5: got the worst pair from 0.22 to 0.58 slack and cost a 9.3-unit-wide
  undercroft under a 6.3-wide pod.
* **moving the ring** from 2.5 units past the fan to the fan's own lip: fixed
  the proportions, did not fix the disparity.

What would resolve it, and was not built: **one shared apron surface with ridge
guides instead of eight walled chutes.** Ridges have no width requirement - the
shelf already steers a marble with 0.11 bumps at 0.63 pitch - so constraint 3
disappears entirely, and with it the length/grade bind. That is the next thing
to try, and it is a rewrite of `_chutes` and `_chute_section` rather than of the
architecture.

---

## 4. Three stall sites, traced

Six seeds, gated, 24 s: **20 of 48 racers through (41.7%)**, 2 to 5 per seed.
Positions at t = 14 s classify the failures into three places:

| where | reading | what it is |
|---|---|---|
| **shelf** | slot 6 at r 3.23, y −0.60, z −1.28, v = 0 | stalled against a fanning ridge at the lip. 22° of divergence is at the edge of what a 0.11 ridge turns rather than stops. |
| **chute** | slots 1, 4 at y −2.46 to −2.61, v = 0 | stalled in the last stretch before a cup, where a shaped profile is shallowest. |
| **cup exit** | slots 0, 5, 7 at r 1.00 to 1.32, v ≈ 0 after the release | released but not leaving. |

Four defects were found and fixed on the way, each of which had frozen the
whole field:

1. **The paddle was shorter than a resting marble's centre.** A cup floor at
   `port_floor` puts a 0.285 marble's centre at `port_floor + 0.285`, and the
   gate's own 0.42 put the paddle's top at exactly that. Every racer rolled
   over it. `PORT_GATE_HEIGHT` is 0.62.
2. **A tangential paddle does not close a cup.** The first build stood it across
   the ring, on the reasoning that a marble would run along the ring into it;
   every marble arrived *radially* off its chute and left over the inner lip.
   The paddle is now the cup's inner wall.
3. **The exit chute's walls came up through the drain.** Starting at
   `drain_lip − 0.05` with full walls from its first ring, they stood 0.46
   *above* the dish's inner floor and made a slot the field wedged in. A chute
   under a drain is a landing and a landing has no kerb: it starts 0.44 lower
   and grows its walls over the first third.
4. **The vanes stood where the marbles come out.** At a foot radius of 1.02 a
   vane is exactly at the cup's inner lip at 0.99. They start at 0.88 now.

And one instrument defect, which is the same class of error the memory note
`instrument-bugs-hide-geometry-findings` records:

5. **The stall detector called a held marble stuck.** `STOPPED_FOR` is 240
   ticks - one second - so every racer waiting for a synchronised release was
   reported stalled before the race began, and the trial "settled" at 3 s with
   every column empty. `StartTrial` now reads the machine's own actuators and
   suppresses stall and containment verdicts until the last gate has finished
   releasing.

---

## 5. A baseline that was mislabelled

`tools/sloped_start_bench.py` builds `start_machine()` with no plan, which is
`SHIPPED_PLAN`, whose `start_kind` field defaults to **`"basin"`** and is not
overridden - while `sloped.course.START_KIND` is `"fan"`. So the 300-seed run
recorded in `docs/validation/sloped_race_v1/v14/start_baseline_fan.json` is the
**basin's** early-rank profile, not the taper's:

    slot        0      1      2      3      4      5      6      7
    descent  6.933  5.940  3.523  4.353  2.490  2.330  4.077  6.353
    span 4.603 places, best slot 5, worst slot 0

That is the basin's centre-heavy V, and it agrees with
`docs/sloped_race_v13_basin.md`'s own table. It is not the number the shipped
course would give. The file is kept with that correction recorded here rather
than deleted, because the mislabelling is the finding: a lab whose "shipped"
plan does not read the course's own `START_KIND` will quietly measure the wrong
geometry, and it did.

---

## 6. What this leaves

`START_KIND` stays `"fan"`. The radial start is reachable as
`start_module("radial", launch)` and as `StartPlan(start_kind="radial")`, both
off by default, so nothing that ships is affected.

Not attempted this session, and untouched: the orange lead transition, the
`leg1[80..99]` and `leg2[80..99]` traps, the fresh full-course benchmark, seed
selection, determinism and the V1.4 render. No fairness claim is made about the
radial start - it has not been benchmarked, because a start that delivers 42% of
its field cannot be.
