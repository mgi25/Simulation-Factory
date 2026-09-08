# V1.7: the dynamic start equaliser, and the trade it cannot escape

**Status: built, does not jam, and improves slot fairness by about half. It
fails the throughput gate — about a tenth of the field is never released — and
the two trade curves that would fix that both spend the fairness gain to buy
it. Reported as section 28's case B, with the mechanism measured.**

The shipped course is untouched: `sloped.course.START_KIND` is still `"fan"`,
the course builds `StartGrid`, and `sloped.course.check()` reports zero
findings. `rotor` is reachable as `start_module("rotor", launch)` and
`StartPlan(start_kind="rotor")`, off by default.

---

## 1. Why the earlier wheel jammed — the answer section 4 asked for

`tools/sloped_start_scan.py` records a wheel that reduced the rank spread and
put 18.8% of the field in the stuck column. The mechanism is a **closing gap**,
and it is arithmetic rather than tuning.

That wheel swept a circle of tip radius 0.90 inside a *straight* channel whose
clear half width is 0.94, so the gap between its tip and the wall is
`0.94 − 0.90 sin(angle)`:

| blade angle | 0 | 20 | 40 | 60 | 80 | 90 |
|---|---|---|---|---|---|---|
| tip to wall | 0.94 | 0.63 | 0.36 | 0.16 | 0.05 | 0.04 |

A marble is 0.570 across, so the gap passes through **exactly one marble
diameter at about 24 degrees — four times a revolution, every revolution.**
That is a scissor, and the recorded numbers are what a scissor predicts: a
faster blade is worse (6.0 rad/s → 18.8% stuck, 12.0 rad/s → 80.2%) because it
closes more often per second, and a wheel further downstream is better
(sample 24 → 5.2%) because the field crosses the pinch zone quicker.

**A chamber concentric with its rotor cannot do that**, because the gap has no
angle in it. That single fact is why the rotor moved out of the channel, and
`tests/test_sloped_shuffle.py` pins it at every 15 degrees of rotation.

---

## 2. What was built

    eight bays abreast on a flat pan, one synchronised gate   <- unchanged, seen
      |  a short apron, which may taper - section 2 is why
    a circular chamber 5.40 across, 7-degree conical floor
      |  four paddles, 1.10 to 2.55, 5.0 rad/s, 1.19 turns
    the field circulates, collides and exchanges places
      |  the rotor stops; the field settles against the ring
    a gate ring in twelve segments drops 1.80
      |
    a 1.90-wide central outlet, then a chute onto the launch

The architecture's one rule is section 2's: **the exit stays shut while the
mixing happens.** With it shut, "distance to the exit" is not a quantity the
field can be sorted by while it is being stirred. That is also why the entry
*may* taper — what an entry constriction orders is discarded before anything
can be sorted by it.

Every clearance a marble could be caught in is constant, and each sits well
clear of the dangerous band:

| | | |
|---|---|---|
| tip to wall | 0.150 | 0.26 marbles — swept, cannot be entered |
| paddle root to gate ring | 0.150 | 0.26 marbles — likewise |
| between paddles at the root | 1.728 | 3.03 marbles — passes freely |
| under a blade, at its root | 0.208 | 0.36 marbles — nothing fits under |
| free radial travel | 1.180 | **2.07 marbles — the field can pass itself** |
| chamber against field area | 9.8× | 20.1 against 2.0 |

The last is the sizing that matters, and it is what V1.5's trough failed: eight
marbles at one radius in a channel one marble wide cannot exchange cyclic
order, so a stirrer can only rotate the necklace. Two diameters of radial
freedom is what lets the rotor actually reorder them.

`START_LIFT` is derived at **2.14**, against the radial start's 4.30.

### Section 7: a fixed rotor phase does produce bias, and the seed fixes it

Traced with one marble at a time and a fixed phase, every racer came to rest at
one of **four bearings 90 degrees apart** — 40.4, 130.4, 220.4, 310.4 — being
wherever the paddle that last touched it stopped. Quantised parking is a
geometric sector by another name, and a geometric sector is what the previous
five topologies died of. Deriving one *global* angle from the seed removes it,
and the 96-seed table below shows the difference: the centre correlation falls
from −0.447 to −0.182 and the span from 2.490 to 2.200.

---

## 3. The measurement

96 seeds, 768 racers, same instrument, same downstream. "held" is the fraction
still in the chamber when the trial ended.

| | lost | held | **delivered** | exit span | **slot r** | **centre r** |
|---|---|---|---|---|---|---|
| fan, as shipped | 0.65% | 0% | **99.35%** | 2.927 | **−0.387** | **+0.574** |
| rotor, fixed phase | 1.30% | 11.07% | 87.63% | 2.490 | −0.177 | −0.447 |
| rotor, seed phase | 1.43% | 9.64% | 88.93% | **2.200** | **−0.206** | **−0.182** |

**The fairness gain is real.** The slot correlation roughly halves (−0.21
against −0.387), the rank span falls a quarter, and the shipped taper's strong
*centre* bias — +0.574, the shape that survived every passive attempt — drops
to −0.182, a third the magnitude. No bay is consistently first or last.

**The throughput gate is not met, and not nearly.** Section 11 asks for 99.5%;
the mechanism delivers 88.9%. It does not *jam* — the chamber's clearances
are constant and nothing wedges — it simply fails to release about a tenth of
the field before the trial ends.

### The blind spot that hid it, and section 4's real lesson

The first runs of this chamber reported `lost 0, stuck 0` and looked clean.
They were not: `StartTrial._where` is only set once a marble has touched the
launch or leg1, and `_stall` only recorded a verdict for a marble that had a
location — so a start that **never delivers** left every racer unrecorded.
Both this chamber at two positions and V1.5's converging funnel reported a
clean sheet while delivering **zero of 192 racers** to the first checkpoint.

`_stall` now books an undelivered racer to `("start", 0)`. Every throughput
number in this document is post-fix; the pre-fix ones were fiction. This is the
third session in a row in which the instrument, not the geometry, was the thing
that had to be corrected first — see the memory note
`instrument-bugs-hide-geometry-findings`.

---

## 4. The trade the mechanism cannot escape

Two independent levers fix the throughput, and both spend the fairness gain.
Full tables in `docs/validation/sloped_race_v1/v17/trade_curves.txt`.

**The chamber floor's tilt** (48 seeds each):

| tilt | held | exit span | slot r | centre r |
|---|---|---|---|---|
| 7° | 7.55% | 2.52 | −0.294 | −0.166 |
| 11° | 13.54% | 0.94 | −0.288 | −0.349 |
| 15° | **4.69%** | 2.02 | +0.135 | **+0.643** |

Not monotone, and 15 degrees is the tell: **a floor steep enough to deliver the
field is a floor that packs it against the closed outlet while it is being
mixed**, where the paddles cannot get between the marbles. Throughput improves
and the centre correlation climbs to +0.643 — the shipped taper's own bias,
recreated by the very gradient that was supposed to serve the outlet.

**A slow tail sweep**, the rotor slowing to a crawl rather than stopping dead
(48 seeds each):

| tail rate | delivered | exit span | slot r |
|---|---|---|---|
| 0.0 | 91.41% | 2.58 | **−0.100** |
| 1.2 | 91.67% | 3.75 | −0.696 |
| 2.2 | **96.35%** | 2.48 | −0.866 |

Monotone in the wrong direction. Every unit of sweep that buys throughput costs
slot fairness, and at 2.2 the correlation is worse than the taper's.

**The mechanism common to both**, and it is the finding:

> The chamber destroys the bay-to-position map while the exit is shut. But
> *delivering* the field to the exit requires a rule that reads where each
> marble is — a gradient, or a sweep — and the field's positions still carry
> whatever the mixing left of the bay. The better the delivery rule, the more
> of that residue it reads back out.

Three further corrections were needed on the way, all recorded in the code that
carries them: the rotor must **stop** before the outlet opens (spinning, it
centrifuges the field outward and six of eight racers simply stayed put); the
outlet must be **1.90 across** (at 1.50 the field arched over it, exactly as
V1.5's 1.24 drain did); and the gate ring must drop **1.80** rather than 0.80,
or it retracts into the chute's mouth and stands there as a fence.

---

## 5. Conclusion

Section 28's stop condition, case B. The mixer is not falsified on fairness —
it is the first start in seven attempts to reduce both the slot correlation and
the centre bias at once. It is falsified on **throughput**, and the two levers
that would fix the throughput are measured to spend the fairness.

Sections 16 to 26 — the orange lead, the `leg1[80..99]` and `leg2[80..99]`
traps, the fresh 600-seed benchmark, seed selection, determinism, the replay and
`real_race_v16.mp4` — are gated on the start passing. They are untouched.
V1.3's numbers remain the current baseline and the shipped `fan` start is
unchanged.

What this leaves for a next attempt is narrower and better posed than anything
the passive sessions left. The chamber's mixing works and does not jam; only
its *emptying* is bay-correlated. So the next mechanism should **empty the
chamber by a rule that does not read position at all** — the floor dropping
away beneath the whole field at once, rather than a gradient or a sweep
persuading each marble to find the hole. That is a second moving part, not a
different architecture, and it is the one place the measurement points.

### Remaining issues

1. About a tenth of the field is never released at the fairest configuration.
   The trade curves say where the throughput is, and it is not free.
2. `leg1[70..89%]` loses racers in every configuration measured here and in
   V1.6, the shipped taper included. That is the pre-existing `leg1[80..99]`
   trap, still open, and it contributes 8 to 10 of each 96-seed run's losses.
3. The realised exit-chute grade is 2.7 degrees shallower than the target
   `CHUTE_GRADE` that sizes the lift, because the chute's landing sits 0.24
   below the outlet's lip and `derived_lift` does not account for it. Harmless
   — the shallower surface is the measured and better one — but the two names
   should agree.
