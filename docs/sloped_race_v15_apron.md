# V1.5: the shared apron works, and the radial architecture does not

> **Followed by `docs/sloped_race_v16_widelaunch.md`, which closes the
> question.** Section 4 of this report names the untested quadrant - a start
> with no constriction at all - and V1.6 built it. The wide field produces more
> lateral crossover than the shipped taper does, and the slot correlation more
> than doubles, because a 5.6-wide channel through 90 degrees of turning makes
> the inside line 8.8 units shorter than the outside. Passive start geometry is
> now considered exhausted.

**Status: the apron the V1.4 report asked for is built and delivers 100% of the
field to the ring with both fairness invariants exact. The radial start is
nevertheless *less* fair than the taper it was meant to replace, and this
document contains the measurement and the argument for why that is structural
rather than a tuning failure.**

The shipped course is untouched. `sloped.course.START_KIND` is still `"fan"`,
`sloped_course()` builds the same thirteen modules, and no number in
`docs/sloped_race_v13.md` changes. The radial start is reachable as
`start_module("radial", launch)` and `StartPlan(start_kind="radial")`, both off
by default.

---

## 1. The benchmark harness, corrected first

A `StartPlan`'s `start_kind` defaulted to `"basin"` while
`sloped.course.START_KIND` said `"fan"`, and `tools/sloped_start_bench.py`
built the default plan with no argument at all. So V1.4's "fan" start baseline
was the basin's, and a basin ignores every other field on a plan - fins,
stagger, deflectors, tray, fall profile, launch width - so the mislabelling
substituted a different machine rather than a different label.

Four gates now stand between a named start kind and a recorded number:

| gate | where |
|---|---|
| each start class declares its own `START_KIND`; `start_module` builds from one table and checks the module's answer against the request | `sloped/course.py` |
| `StartPlan.start_kind` has no default, and `__post_init__` refuses a plan that leaves it implicit or names a kind that does not exist | `sloped/startlab.py` |
| `start_machine` asserts the instantiated module's kind against the plan's, and records what it built on the machine | `sloped/startlab.py` |
| every `TrialResult` carries the kind, `summarise` refuses to average two topologies together and reports the kind, and `--start-kind` is required and appears in the header and the JSON | `sloped/startlab.py`, `tools/sloped_start_bench.py` |

`BENCH_PLANS` holds one plan per topology behind the *same* shipped mixer and
shuffle wheel, so a fan-versus-radial comparison differs only in the start.
All 45 fan-family candidates in `tools/sloped_start_scan.py` now say `"fan"`
explicitly: they were measured on the fan before the field existed, and between
its introduction and this session a re-run would have built 45 identical plain
basins under 45 different names.

Two further instrument defects were found and fixed on the way, both of the
class the memory note `instrument-bugs-hide-geometry-findings` records:

* **`run_trial`'s duration did not include the hold.** Fourteen seconds of
  racing measured on a start that opens at 0.30 is twenty measured on one that
  holds until 5.60. It is read off the machine's own actuators now.
* **`summarise` crashed on a start that delivered nothing.** A report that
  cannot describe a total jam cannot describe the case most worth describing.

No historical result is rewritten. `start_baseline_basin.json` keeps its file
and its correction in its own `label` field, because the mislabelling is the
finding. **Tests:** `tests/test_sloped_start_kind.py`, 19 of them.

---

## 2. The shared apron

V1.4's eight independently walled chutes delivered 41.7% of the field, and
section 3 of that report records why they cannot be made to fit: a walled chute
needs clear width over a 0.57 racer plus a wall each side, and eight of those
cannot simultaneously satisfy clearance, mutual separation, a grade above the
stall threshold and a grade below a fall, in the two units of plan available.

`sloped/apron.py` and the rewritten `sloped/radial.py` replace them with one
continuous surface carrying eight guide grooves and no walls.

| | |
|---|---|
| delivery to the ring | **100%** (96 of 96 racers, twelve seeds); 99.0% over a second twelve |
| drop, pan to trough | spread **0** (one derived number, not eight) |
| radius from the drain at rest | spread **0** by construction; **0.004..0.036** measured |
| height at rest | spread **0.001..0.006** measured |
| guide length | 3.61..7.88, spread 4.27, **ratio 2.18** (V1.4: 22.7) |
| local grade | **8.7..38.2 deg**, every guide in band |
| worst uphill step along any guide | **+0.000000** |
| apron width | **5.57**, inside the drawn pod's 6.30 (V1.4 needed 9.3) |
| `START_LIFT` | **4.30**, the figure the brief approved, not more |
| mesh | 7351 vertices, 12298 triangles, **0 findings** |

Three things about how it is built are worth keeping.

**The guides are solved, not drawn.** Four authored parametrisations were tried
and every one failed the same way: *a rule puts a corner wherever it clamps,
and the corner then reads as a curvature finding that belongs to the rule and
not to the route.* Radii clamped to a clearance floor reported 0.03-unit
curvature radii; a floor stepping by one lane where an inner route ended
reported 0.26; a step from foreign-sector clearance to cup radius at a sector
boundary reported 0.31. Solved - smooth, project into the feasible band, repeat,
innermost bay first - the same routes hold 0.31 to 1.02, and nesting is true by
construction rather than checked afterwards. Two further lessons are recorded in
the methods that carry them: **length must not be driven from inside the
smoother** (a path can always buy length by looping; a length-seeking term
returned 47-unit routes for a six-unit problem), and **separation must be a
floor, not a push** (a push makes a route chase its neighbour round the ring: it
put bay 0 into an 18.7-unit spiral and *reduced* the worst separation to 0.013).

**The guide starts at the resting bay, not at the shelf's lip.** Every earlier
attempt treated the transport as a stage beginning at the lip, and so had to
force each route's entry tangent to match the heading the shelf delivers, and
had to equalise the *apron* lengths on their own - 2.2 to 6.8, a ratio of 2.8
that no meander closed, because the near cups sit in a wedge between the lip
line and the ring that is 0.15 units wide where they are. Solved as one curve
from the resting bay, there is no join to get wrong and the run every bay shares
dilutes the difference: 2.8 becomes 2.18. **The shared upstream run is itself
the equaliser**, and it is a better one than meandering, which is
curvature-limited: a marble arrives at the lip at 10 layout units per second and
a shallow groove holds it round a bend of 0.85 at best.

**The ring is a continuous inward-tilted trough, not eight walled cups.** That
is a departure from section 2 of the brief and it is measured. A cup is a
pocket, so on a single-valued surface a route may not pass over a foreign one;
so each route must hold outside the rim until its own sector and then descend
0.70 in radius inside its own 45 degrees. At the radius available that is a turn
of about 0.30 units taken at 18 layout units per second, and holding it needs 83
degrees of side slope. Measured across four parametrisations the number came out
0.25 to 0.32 every time. The trough removes the constraint instead, and
strengthens the invariants: every racer rests against the *same* gate ring, so
its radius from the drain is `PADDLE_R + MARBLE_RADIUS` exactly rather than
"somewhere inside its own pocket", and everything below the trough can be
rotationally rather than eight-fold symmetric.

### Six defects, each of which had cost most of the field

Every one was found in simulation, and none of them was visible in the geometry
check that ran before it:

1. **the outer kerb stood 0.30 off the last guide with no floor between**, so
   bay 0's marble had a hole under its outboard half. It never moved at all, for
   the whole run, every seed. The kerb is a floor that rises now.
2. **the groove was a cosine rib 0.24 tall across a 0.63 lane**, whose curvature
   radius at the bottom is `W^2 / (2 R pi^2)` = 0.084 - smaller than the 0.285
   marble - so the marble bridged the V on two flanks instead of reaching the
   floor. It is a 0.60 circular cradle now. The basin's notes record the same
   arithmetic in a different shape.
3. **the crest was scaled to the strip width**, and the strips widen from 0.63
   at the line to 1.34 at the ring, so the crest rose along the flow. *A crest
   that rises along the flow is a transverse ridge*: both outer racers climbed
   0.18 of one at 3.25 units from the drain and stopped there for eleven
   seconds. The local-minimum check missed it because a ridge is not a basin -
   there is always a way downhill sideways, just not forwards. The crest is
   capped at one height.
4. **there was no floor behind the resting line.** The apron began at the
   guides' own start, and the drawn pod's floor runs 0.66 further back. The
   release itself jostled four of eight racers into the hole.
5. **the release paddles were inherited from `StartGrid`**, which places them
   from the fan's trough geometry. They stood out on the apron, downhill of the
   field: bay 7 ran into one and stopped. Bay 0's cleared by a hair, which is
   why the failure looked like a left-right asymmetry in a geometry that is
   exactly mirror-symmetric - and *that* is what identified it.
6. **the 45-degree sector the drain empties through was open at apron level**,
   and the two outermost guides deliver at its edges. Bay 0 reached the trough
   and was knocked straight out through it, ending 3.9 units from the drain and
   4.7 below the pan. It has a catch basin now.

`RELEASE` is 5.60, set from the measured time for the whole field to *seat*
(2.20..4.87s over twelve seeds) rather than from the rolling time down the
guides (2.16..4.38s). A marble that has reached the trough still has to find a
bearing of its own among seven others and stop moving.

**Tests:** `tests/test_sloped_apron.py`, 18 of them, pinning the two exact
invariants, the non-crossing and non-climbing properties, the exact east-west
mirror, and defect 5.

---

## 3. The radial start is less fair than the taper. The mechanism.

Both starts, same instrument, same 24 seeds, same downstream mixer and shuffle
wheel - which is what `BENCH_PLANS` exists to guarantee:

| | fan (shipped) | radial |
|---|---|---|
| lost | 1.042% | 1.562% |
| early-rank span | **3.167 places** | **4.583 places** |
| best / worst slot | 6 / 0 | 0 / 4 |

The slot table names the mechanism without ambiguity:

    slot        0      1      2      3      4      5      6      7
    bearing 112.5  157.5  202.5  247.5  292.5  337.5   22.5   67.5
    rank     2.63   3.21   3.13   6.21   7.21   5.63   4.33   3.67

Bays 3 and 4 deliver at 247.5 and 292.5 - the two bearings furthest from the
exit chute's mouth at 90 - and they are last in every seed. Bays 0 and 7, at
112.5 and 67.5, are nearest it and first.

**Equal radius and equal height are not sufficient, because a marble's bearing
round the ring survives the drain.** It falls where it was standing, lands that
far along a chute that runs one way, and a 1.9-unit spread on a 2.9-unit chute
decides the order. This is the taper's mechanism and the basin's, one stage
further down: *a single common exit orders the field by distance to that exit.*

### Why the bearing cannot be decoupled from the bay

This is the part that makes it structural rather than a knob:

1. All eight must rest at **one radius** - that is the invariant that makes
   distance-to-the-exit equal, and it is the whole point of the architecture.
2. Eight bodies on a circle at one radius, in a trough one marble wide, **cannot
   exchange cyclic order** without leaving that radius. Widening the trough
   enough to pass would let a marble rest behind another, at a different radius,
   which destroys (1).
3. The eight guides must arrive at eight distinct bearings **in the cyclic order
   that matches the bay order**, because on a single-valued surface the guides
   cannot cross, and the nesting that avoids crossing is ordered by sweep
   magnitude - which is ordered by bay.
4. Therefore the resting cyclic order **is** the bay order, up to a rotation.
   Measured: the resting bearings drift 0.1 to 58 degrees from their delivery
   bearings, mean 12 to 35 over three seeds - substantial jitter, and the cyclic
   order preserved in every seed.
5. A single exit leaves at one bearing, so distance from a marble's bearing to
   it is a function of its place in the cyclic order - hence of its bay.

Rotating the bay-to-bearing map does not help: it changes which bays are
advantaged, not that some are. Reversing it breaks (3).

### The remedy, and why it does not work either

The only escape from (5) is to converge the field to a *point* before the
chute. `RadialStart.FUNNEL = True` builds it: a steep cone from the trough's
inner edge to a throat one marble wide, with eight vanes to spiral the field
through rather than let it arch over. Geometrically it is correct - every racer
begins that descent at the same radius, travels the same distance, and past the
throat they are all in the same place.

**Physically it serialises the field.** Measured at throat radii 0.40, 0.44 and
0.62 and throat depths 0.22 and 0.68:

    zero of 192 racers reached the start lab's first checkpoint - 9% of the
    course - within fourteen seconds of the release, against 192 of 192 with
    the wide drain.

Traced directly, six seconds after the release the field is still strung
vertically through the cone with two or three racers on the chute and the rest
stacked above them. Deepening the throat past a marble diameter fixed the
*arch* - at 0.22 a marble in the throat was still part of the arch above it -
and left the *queue*, which is the real obstacle: a one-marble throat passes one
marble at a time, and eight marbles metered through it arrive spread over
several seconds. That is not a race, and it is not fast enough for the window
either.

The flag is kept rather than deleted, because a falsification nobody can re-run
is an assertion.

---

## 4. What this leaves

`START_KIND` stays `"fan"`. Nothing that ships is affected.

Per section 14 of the brief the orange lead transition, the `leg1[80..99]` and
`leg2[80..99]` traps, the fresh full-course benchmark, seed selection,
determinism and the V1.4 render are **gated on the start passing**, and it does
not pass. They are untouched, and V1.3's numbers remain the current baseline.

The radial architecture is falsified for slot fairness, in the specific sense
that its own defining invariant - one radius for the whole field - is what
forbids the one further thing it would need. **Three topologies have now shown
the same mechanism**, and the general statement the three of them support is
stronger than any of them alone:

> A start that delivers its field to a single exit orders the field by distance
> to that exit. Making the distances equal is not enough: whatever coordinate
> the equalisation leaves free - lateral position in the taper, position along
> the notch in the basin, bearing round the ring here - is still a function of
> the bay, and the exit still reads it.

What that leaves untried, and what a fourth attempt should be aimed at, is the
one thing all three share and none has varied: **the field is delivered to the
course as a pack whose order is set at a constriction.** The fan's own scan
found the counter-example already and rejected it for the wrong reason -
`launch_width`, the wide mixing stretch on the launch itself, where the
convergence happens on a 25-to-43-degree descent instead of in a 1.7-degree
trough. `lw-*` candidates lost 34% of the field at the *convergence*, not in the
wide stretch. A start with no constriction at all - eight bays that never
converge, feeding a channel wide enough to carry eight abreast until the course
itself mixes them - is the untested quadrant, and it is a change to the launch
rather than to the start.

### Remaining issues

1. Two geometry-check findings stand, both about crowding near the delivery end:
   guides 0 and 1 pass within 0.536 against the 0.64 a rib needs, and route 1
   passes 0.471 from route 2's delivery point. Throughput is 100% regardless and
   section 6 of the brief permits racer contact, but they are real and reported.
2. The apron wants up to 38 degrees of bank that it does not have. The grooves
   hold the field while it is slow and let it drift on the fast bends; the
   trough absorbs that, but a lane's *identity* is not maintained to the ring.
3. One racer in 96 perches on top of a seated one instead of finding a bearing
   of its own, and is then released from the wrong radius.
