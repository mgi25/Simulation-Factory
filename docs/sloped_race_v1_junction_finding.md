# The split and the merge do not join, and the arithmetic that says so

Recorded before any geometry was changed, because section 7 of the brief asks
for that: the macro layout is frozen, physics-driven corrections are allowed,
and a change that materially alters the visible silhouette has to stop and be
written down first. This is that note. It is a finding, not a proposal to
redesign the course.

## What was measured

`sloped.pathing` is a sample-for-sample port of the GDScript that built the
photographed course, and `sloped.contract` proves it: all 182 recorded
centreline points of all seven runs agree to **0.00084** layout units - the
rounding in the JSON writer - and every recorded length, drop, clear width,
floor offset, bank extreme and module anchor agrees exactly. So the numbers
below are the built course's own, not an approximation of it.

Direction of travel is `atan2(dx, dz)` in degrees, the convention the layout
table itself uses. The layout JSON records these as *unsigned* magnitudes
(`_dump_physics` calls `Vector3.angle_to`), which is why the defect is not
visible in the contract file: blue's entry is recorded as `63.91` and is
actually `-64.13`.

### The five joins that work

| join | position gap | heading change | bank at the seam |
|---|---|---|---|
| launch → leg1 | 0.0000 | 79.41° → 81.72° | 0.00° → 0.00° |
| leg1 → leg2 | 0.0000 | −88.22° → −82.53° | 0.00° → 0.00° |
| leg2 → leg3 | 0.0000 | 82.41° → 79.56° | 0.00° → 0.00° |
| leg3 → **blue** | 1.1147 | −84.40° → −64.13° (**20.3°**) | 0.00° → 0.00° |
| **blue** → final | 1.1554 | 72.58° → 65.11° (**7.5°**) | 0.00° → 0.00° |

The three leg seams are exact - the runs share a control point and `auto_bank`
eases both sides to level, so the channel is continuous in position, tangent
and roll. Blue joins at 20° and leaves at 8°. Nothing here needs correcting.

### The two joins that do not

| join | heading change | what a marble would have to do |
|---|---|---|
| leg3 → **orange** | −84.40° → **+68.36°** | **152.8°** |
| **orange** → final | **−74.26°** → 65.11° | **139.4°** |

The field arrives at the split at (6.0, 10.6, 17.8) travelling **west**. The
blue mouth is at x = 5.20, further west, and blue's lobe runs west: a marble
carries straight on into it. The orange mouth is at x = 6.90, *behind* the
arrival, and orange's lobe runs east out to x = 21.0 before hooking back. To
enter it a marble has to reverse.

The merge is the same defect mirrored. Blue arrives at (−1.1, 4.9, 36.05)
travelling east at 72.6° and the final sprint leaves at 65.1°: a 7° kink.
Orange arrives at (+1.1, 4.9, 36.05) travelling **west** at −74.3°. The two
branches converge **head-on**, 147° apart, and the exit runs east between them.

The bisector arithmetic is what makes this unambiguous rather than a matter of
degree. At the split the two mouths fan symmetrically about **+2.15°** - almost
exactly +Z, straight downhill - so a stem arriving along +Z would feed both
lobes evenly and fairly. The stem arrives 86° off that bisector. At the merge
the two arrivals bisect at **−0.85°**, again almost exactly +Z, and the exit
leaves 66° off it. Both stations were composed as symmetric Y-junctions and
both are fed across the axis of their own symmetry.

## Why it survived the visual review

Because the still frames do not show direction of travel. In
`docs/validation/sloped_course/final_run.png` the blue and orange channels are
two roughly parallel ribbons crossing the frame and the warm final sprint
leaves at the lower left; nothing in that composition says which way anything
is moving. `split.png` shows a fork with a portal over each mouth, and a fork
photographed from in front looks the same whichever branch is reachable. The
locked branch said so itself, in the JSON and in its own report: *"the start
grid, the mixer pin rows and the two branch lengths are shapes, not proofs"*,
and the merge was already named as the weakest module. This is what it was the
weakest at.

## What this costs, and what it does not

It does not touch the through route. START → launch → leg1 → leg2 → leg3 →
**blue** → final → FINISH is 195.98 units of physically continuous channel with
five clean seams, and it is the majority of the course by length and all of it
by silhouette. The 34° launch, both hairpins, the spinner corridor, the violet
sweep, the viaduct and the finish arena are unaffected.

It costs the second route. `orange` is 40.96 units - 21% of the route - and as
authored it is reachable only by reversing a rolling marble twice.

## The three ways out, and the one taken

**Turn the stem.** Continue leg3's hook another 86° so the field arrives down
the +Z bisector and both lobes are entered at ±66°, symmetric and fair by
construction. Correct, and it does not fit: the hook would need about four
units of radius at the measured arrival speed and the branch mouths are 0.78
units downstream of leg3's exit, so the turn overshoots them. It also
re-authors the visible violet sweep, which is one of the seven section stills.

**Re-aim the lobe.** Move orange's first and last control points so its mouth
and tail point into the flow. Impossible without moving the lobe: the body sits
east of the split and returns west to the merge, so both of its ends can only
be entered from the direction they already face. Re-aiming the ends without
moving the body just moves the reversal a few units along.

**Turn the flow at the two stations.** A compact banked turn-around inside each
station's own footprint: one at the split that takes the westward arrival round
onto the fork's axis, one at the merge that brings orange's westward arrival
round onto the sprint's. This is the option taken. Section 7 lists "merge
geometry correction" and "physically necessary guard changes" among the allowed
physics-driven corrections and section 23 lists "turn radius"; the two stations
are 9.2 × 12 and roughly 4 × 2.4 layout units of existing pad and housing, so
the added geometry sits on ground the course already occupies, and neither is
visible in the hero frame.

**It is still a material change to two of the seven section frames** - `split`
and the merge end of `final_run` - and that is the reason this file exists
rather than a commit message. The sizes are derived from the measured arrival
speed at each station rather than chosen, and both are recorded in
`docs/sloped_race_v1.md` with the before and after.
