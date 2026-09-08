# V1.6: the unconstricted start, and why passive start geometry is exhausted

**Status: built, measured, and falsified. The wide field produces real lateral
crossover - more than the shipped taper does - and the slot bias more than
doubles. The mechanism is measured, it has a confirmed dose-response, and it is
structural.**

The shipped course is untouched. `sloped.course.START_KIND` is still `"fan"`,
`sloped_course()` builds the same modules and `sloped.course.check()` reports
zero findings. `wide_launch` is reachable as `start_module("wide_launch",
launch)` and `StartPlan(start_kind="wide_launch")`, off by default.

---

## 1. What was tested, and why this was the last passive candidate

Four topologies had been measured and all four ordered the field.
`docs/sloped_race_v15_apron.md` states the shared mechanism:

> A start that delivers its field to a single exit orders the field by distance
> to that exit. Making the distances equal is not enough: whatever coordinate
> the equalisation leaves free is still a function of the bay, and the exit
> still reads it.

|  | the coordinate the equalisation left free |
|---|---|
| taper (V1.1) | lateral position in the trough |
| basin (V1.3) | position along the rim notch |
| radial ring (V1.4/1.5) | bearing round the ring |

The one thing all three share, and none of them varied, is that **the field is
serialised near the start**. So the last untested passive hypothesis is the
absence of that: keep the course wide enough for real lateral motion long
enough for collisions and overtakes, and narrow only after the starting order
has decorrelated.

`sloped/widelaunch.py` builds it:

    eight bays abreast on a flat pan, one synchronised gate    <- unchanged, seen
      |
    one broad apron, no lane walls, no grooves, 5.7 wide       <- the change
      |
    the launch, held open 2.6 times and banked no more than 6 degrees
      |
    leg1, held open through its gentle first stretch
      |  eighteen units of gradual narrowing, ending before leg1[80]
    the 1.88 hero channel

**There is no taper anywhere in it, and that is a property of the numbers
rather than a choice.** The drawn pod is 5.46 wide across the gate and the
launch's own entry widened 2.6 times is 5.57, so the apron between them runs at
constant width: `START_BACK_HALF` is 2.73 and `0.5 * HERO_CLEAR_WIDTH *
widths[0] * 2.6` is 2.786. Nine to ten marbles fit abreast the whole way.
`START_LIFT` is **derived, not inherited** - 1.06 against the radial start's
4.30 - because the apron needs only enough elevation to run its 7.88 units of
plan at its own grade profile.

---

## 2. The measurement

Five configurations, one instrument, 48 seeds each, 384 racers each. `wide` is
mid-launch where the field is at its widest; `exit` is the lab's end.
`slot r` is the correlation between bay index and mean rank; `lateral order
kept` is the correlation between where a racer started across the pan and where
it is across the course - **1.0 means the field translated but did not mix.**

| | lost | span @wide | span @exit | slot r @exit | centre r @exit | mean reach | lateral order @exit |
|---|---|---|---|---|---|---|---|
| **fan, as shipped** | **0.52%** | 2.854 | 2.729 | **−0.418** | +0.738 | 0.770 | −0.030 |
| fan, devices removed | 3.13% | 2.812 | 3.229 | −0.411 | +0.694 | 0.770 | +0.067 |
| A `open-sweep` | 11.46% | 6.250 | 3.208 | **−0.979** | +0.068 | 0.953 | −0.029 |
| B `deflectors` | 10.94% | 6.250 | 2.167 | −0.898 | +0.329 | 0.936 | +0.058 |
| C `cross-flow` | 9.12% | 5.125 | 2.188 | −0.964 | +0.114 | 0.954 | −0.019 |

Read the three things that matter.

**The lateral crossover is real, and larger than the taper's.** Mean reach
0.94-0.95 of the half width against the fan's 0.77 - racers get to the edge of
a 5.6-wide field and back. 94-98% cross the midline. And the lateral *order*
correlation ends at about zero in every candidate, so the field genuinely
reorders itself across the course. Section 8 of the brief is satisfied and
measured: a racer starting on the left does reach the right half before the
narrowing.

**And the slot bias more than doubled.** `slot r` at the exit is −0.90 to −0.98
for the wide candidates against −0.42 for the shipped taper. The bay predicts
the finishing order *better* on the open field than in the funnel. The span
falls for B and C - 2.17 and 2.19 against the taper's 2.73 - but a smaller span
with a stronger correlation is a more tightly determined order, not a fairer
one: the ranks are compressed and still in bay order.

**The shape of the bias changed.** The taper's is centre-versus-edge
(`centre r` +0.74, `slot r` −0.42, worst slot 0, best slot 2). The wide field's
is a pure monotone left-right gradient (`slot r` −0.98, `centre r` +0.07, worst
slot 0, best slot 7). That is the signature of the mechanism below.

---

## 3. The mechanism: width times curvature

The wide stretch - the launch plus leg1's first 22 samples - **turns 90.2
degrees in plan**. On a channel 5.57 wide, the inside line is therefore

    2 * 2.786 * radians(90.2) = 8.77 layout units

shorter than the outside line. The resting field is 4.41 wide, and the whole
wide stretch is about 40 units long. So the path-length difference *across the
field* is **twice the width of the field itself**, and a fifth of the stretch's
own length.

Lateral position maps to path length; lateral position is the bay. Bay 0 starts
on the outside of the turn and finishes last in almost every seed.

**Widening the course does not remove the exit-distance mechanism. It replaces
"distance to the throat" with "distance around the bend" - and unlike the
throat, this one gets worse the more of the remedy you apply.**

`docs/validation/sloped_race_v1/v16/width_probe.txt` is the dose-response, one
probe at three widths with the layout otherwise identical:

| factor | width | inside/outside gap | slot r @wide | slot r @exit |
|---|---|---|---|---|
| 1.4 | 3.00 | 4.72 | −0.650 | −0.724 |
| 2.0 | 4.29 | 6.75 | −0.888 | −0.834 |
| 2.6 | 5.57 | 8.77 | −0.952 | −0.977 |

The correlation rises monotonically with width. The extra width that is
supposed to buy lateral mixing is what strengthens the bias.

### Why it cannot be placed somewhere straighter

The turning is not spread evenly, so the obvious repair is to put the open
field where the course is straight. Measured per stretch, the inside/outside
gap a 5.57-wide field would have:

| stretch | arc | turn | gap |
|---|---|---|---|
| launch[0..44] | 5.15 | 33.9° | **3.30** |
| launch[77..117] | 5.02 | 5.5° | 0.53 |
| leg1[0..48] | 16.7 | 10.7° | 1.04 |
| leg1[48..80] | 11.2 | 37.2° | 3.62 |

`launch[77..117] + leg1[0..48]` is 21.7 units of nearly straight course - a gap
of 1.58 instead of 8.77. But it begins 5.15 units *after* the start, and the
launch's first 44 samples are the steep 34-degree turning plunge the field must
cross first. Holding the field open only from launch[77] means tapering 5.46 to
1.88 immediately after the gate and re-opening later, which is the early
constriction the architecture exists to remove, plus a second one. **The start's
node and the launch's first turn are both frozen geometry, and they are 5 units
apart.**

### And the throughput gate was not met either

9.1-11.5% lost against the required 0.5%. The loss sites separate cleanly:

* `leg1[70..89%]` - 22 to 24 of each candidate's losses, and **the
  device-stripped taper loses there too** (8 of 12). This is the pre-existing
  `leg1[80..99]` trap section 20 of the brief already lists.
* `launch[80..99%]` - 9 to 21 per candidate, and the fan has none. This is the
  wide field's own: the seam and the launch's end, where a fast field spread
  over 5.6 units meets the narrowing.

Losses inside the start region proper are 1.6% (A) and 2.1% (C) - still over
the gate, and not the reason the architecture fails.

---

## 4. Six corrections made on the way, and two are instrument bugs

1. **No floor behind the resting line.** A marble seeded on the mesh's first
   row has its contact facet ending under its own centre, so it tips
   *backwards* off the edge: bays 1 and 2 rolled uphill out of the machine and
   fell 17.7 units, while five of eight happened to tip forwards and ran the
   whole lab. V1.5's radial apron had the identical hole in a different shape,
   and it was written up. Twice-learnt.
2. **The alignment grooves were a sampling error, not guidance.** The apron's
   cross-section is carried by the channel's own profile, which has five points
   per cradle half - so on a 5.57-wide field the floor was sampled every 0.70
   units while the bays are 0.63 apart. The groove function was never evaluated
   at a bay centre at all, and what it built was a single 0.089 bump on the
   centreline. Bays 3 and 4 rest on that bump's flank; they moved 0.13 and
   stopped, taking 7th and 8th in every seed with the two lowest collision
   counts in the field. The grooves are gone - which is also section 6's actual
   requirement - and the floor is resolved at 24 points.
3. **The shipped downstream stops being a control when the channel widens.**
   The shuffle wheel's blade reaches 0.90 layout units from the centreline and
   the mixer's pins 1.14, against a half width of 2.38 once the launch is open.
   Both stop spanning the course and become obstructions in front of the centre
   bays only. Keeping the same devices at the same samples is a control only if
   they still do the same thing. The wide candidates carry none, and `BARE_FAN`
   is the matching stripped taper so architecture can be compared with
   architecture.
4. **Bank times width is lateral energy.** The launch rolls 18 degrees, which
   is what holds a marble in a 1.88 channel. Held open to 5.57 the same roll is
   a hill 2.79 units long: a marble crossing it reaches the low guard with 13.1
   layout units per second of lateral speed and clearing the 0.54 guard needs
   10.4. That was 8.85% of the field leaving sideways. A 6-degree ceiling
   leaves 7.6, and it only rolls the section - the centreline, the arc lengths
   and every checkpoint are untouched.
5. **Counting midline crossings is not a mixing metric.** The first version
   reported 95% of racers crossing the midline, which a wide banked field
   satisfies trivially: the whole field slides across together and reorders
   nothing. A metric a bulk translation passes is worse than no metric, because
   it reads as evidence. `lateral_order_correlation` replaced it, and
   `tests/test_sloped_widelaunch.py` pins the case that caught it - a purely
   translated field must report 1.0.
6. **The mesh cache raced on Windows.** Seven benchmark workers meeting a fresh
   content-hash key install it at the same instant; the existence check is a
   TOCTOU and Windows refuses `os.replace` onto a destination another process
   holds open. It surfaced as `PermissionError` part way through a benchmark,
   and only ever on the first run of a new geometry - exactly when a candidate
   is first being measured. `marble3d.mesh.cached_obj` now tolerates it, which
   is correct because the name is a content hash.

---

## 5. Conclusion: passive start geometry is exhausted

Section 25 of the brief sets the stop condition, and this is case B: the wide
launch fails **despite real lateral crossover**, which is measured rather than
assumed - mean reach 0.95 of a 5.6-wide field, 97% crossing the midline, and
the lateral order correlation falling to zero.

Five passive topologies have now been measured, and the general statement the
five of them support is stronger than any one:

> Every passive start delivers its field into a course that reads *some*
> geometric coordinate as a time advantage - distance to a throat, position
> along a notch, bearing round a ring, or distance around a bend. Equalising
> one coordinate leaves another, and the surviving coordinate is always a
> function of the starting bay, because the bays are physically distinct places
> and a passive surface has nothing with which to forget which is which.

The wide launch is the sharpest case because its remedy and its failure are the
same quantity: width buys lateral mixing *and* buys path-length advantage, and
the dose-response shows the second winning.

**The next architecture would have to be a dynamic physical equaliser** - a
mechanism that acts on the field in time rather than a shape that acts on it in
space, so that what it does to a racer is not a function of where that racer
is. Section 17 is explicit that it is not to be implemented in this session,
and it is not.

Per section 18, the orange lead transition, the `leg1[80..99]` and
`leg2[80..99]` traps, the fresh full-course benchmark, seed selection,
determinism and the render are gated on the start passing. They are untouched
and V1.3's numbers remain the current baseline.

### Remaining issues

1. `launch[80..99%]` is the wide field's own loss site - 9 to 21 racers per
   48-seed run, where a field spread over 5.6 units meets the narrowing. Not
   diagnosed further, because the architecture is falsified for fairness and
   fixing its containment would not change that.
2. `leg1[70..89%]` loses racers in *every* configuration measured, the
   device-stripped taper included. That is the pre-existing `leg1[80..99]`
   trap, still open, and it inflates every throughput figure in this document.
3. The shipped taper's own bias is centre-shaped (`centre r` +0.74) and no
   session has yet attacked that shape directly - every attempt has replaced
   the topology instead. It is probably not worth attacking passively, given
   the conclusion above, but it has not been ruled out on its own terms.
