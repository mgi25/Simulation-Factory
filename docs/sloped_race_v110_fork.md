# V1.10 — the fork's overhang, its crest, and where orange actually stops

Status: **the trim and the crest are built, tested and committed. Orange is not
production-viable, and this report says which two things block it and which
hypotheses are now dead.** The shipped route is untouched: `routes="blue"` is
still the default, `START_KIND` is still `"floor"`, and `course.check()` and
`contract.check()` report zero findings on *both* route configurations.

Read [`sloped_race_v19_production.md`](sloped_race_v19_production.md) first.
This report only concerns the fork.

## What V1.9 got wrong, and what it got right

V1.9 concluded orange was blocked on **sorting**: isolated, `0 of 28` marbles
reached orange at any speed or lateral offset, and the ~35.8% usage a full race
showed was traffic shoving marbles east rather than anything choosing to go.
That measurement was correct. Its conclusion — that moving marbles relative to
the crest line meant changing the divider or the guard window, both excluded —
was wrong, because it assumed the crest line was where the geometry said it was.

It was not. There was no crest. There was an **overhang**.

## The defect: orange's lead stood over leg3's channel

Orange's mouth puts its **cradle bottom** on leg3's east cradle edge, and a
channel is 1.65 simulation units wide either side of its cradle bottom. So
orange's whole west half — a marble and a half of cradle, plus its opened west
lip — hung over the east half of leg3's channel. In a vertical section through
the assembled colliders, with the roll taken out so it is the shape gravity
sees:

    step past fork   orange's west edge   clearance over leg3's floor
                 1              -0.250                         0.894
                 2              -0.175                         0.917
                 4              +0.125                         0.868
                 6              +0.625                         0.682
                 8              +1.425                         0.245

A marble is **1.000** across. Every clearance is under it, so the west edge was
not a ledge a marble could pass beneath and not a wall it could climb: it was a
free edge hanging at the height of a marble's own equator, across the half of
leg3's channel the hairpin throws the field into. Over 12 seeds `leg3[84]` lost
8 racers of 96 — reach +1.31 to +1.40 east, vertical speed negative in every
one — and `orange_lead[3..13]` lost 30 more the other way, thrown back west at 7
to 11 units per second off a flank with no wall on it.

`sloped.joins.fork_trim` solves, per orange sample, the profile coordinate where
orange's own surface crosses leg3's east cradle edge, and `TrackRun._trimmed`
folds everything west of it away. Folded rather than deleted: `sweep_rings`
refuses unequal rings, and that invariant is what stops a strip spanning a whole
piece, so the trimmed points are placed *at* the cut and walked down the
section's own `-up` — which at a 26-degree bank points down and **east**, away
from the channel the trim exists to protect. The result is a short skirt under
the seam: a downward-facing wall a marble cannot rest on, in the void the ridge
grows into.

Solved against the built runs rather than tabulated, so a change to the path
law, the bank law or the mouth moves it.

**Measured: the overhang is eight samples long.** The trim table is non-None for
steps 0 to 7 and releases itself from step 8, where orange's own west cradle
edge passes east of leg3's. `FORK_TRIM_WINDOW = 24` therefore solves sixteen
samples past the answer — harmless, but the window is not the mechanism and
should not be read as one. The solve lands on leg3's edge to within `1e-9` at
every active step bar the mouth, which is clamped to the centreline because
there is no crossing there to solve for.

## The crest: what the trim made possible

With the overhang gone the two runs share one edge, so **what stands on that
edge is the only thing between the two routes**. `TrackRun.wall_factor` takes a
sixth window entry — the open fraction — and `sloped.course.FORK_CREST` is it.
Physical geometry, a wall height, nothing per-marble.

That turned the route split into a dial, which is the thing V1.9 said was
unavailable. Scanned against whole races
(`docs/validation/sloped_race_v1/v110/fork_lab_crest_height.json`, and
`fork_lab_crest_fine.json` between 0.09 and 0.21):

    crest   finish   all8   escape   blue use  blue fin   orng use  orng fin
     0.05    0.500   0.00    0.445      0.250     0.375      0.742     0.547
     0.09    0.344   0.00    0.609      0.318     0.311      0.672     0.364
     0.13    0.349   0.00    0.620      0.641     0.406      0.349     0.254
     0.17    0.641   0.08    0.339      0.891     0.702      0.099     0.158
     0.21    0.885   0.25    0.099      0.984     0.894      0.005     1.000
     0.25    0.961   0.81    0.016      0.992     0.969      0.000     0.000
     0.40    0.977   0.81    0.016      0.992     0.984      0.000     0.000
     0.55    0.992   0.94    0.000      0.992     1.000      0.000     0.000
     0.70    0.992   0.94    0.000      0.992     1.000      0.000     0.000

**There is no setting that gives both routes and reliability.** Every crest low
enough to pass real orange traffic collapses the course, and the collapse is not
mostly orange's — read the `blue fin` column, which tracks the crest almost
perfectly from 0.311 to 1.000. A low crest hurts *blue* worst.

The 0.55 and 0.70 rows being identical is expected, not a bug: at both, nothing
crosses, and a marble that never rises above 0.55 cannot tell the two walls
apart.

**Do not read the 0.55 row as an improvement on the shipped route.** It is
127/128 finishers over 16 seeds; V1.9's blue route is 98.83% over 4800 racers.
Those are statistically indistinguishable, and `routes="blue"` does not build
the fork at all, so the trim cannot affect it either way.

## Two blockers, and which is which

Seven configurations x 16 seeds, all at the open crest
(`fork_lab_guards.json`). Losses grouped by region, from each row's top ten
sites:

    configuration               merge  lead  leg3  orange | finish  escape  blue fin
    trim only (as built)           14    10    10       3 |  0.500   0.445     0.375
    guards close at 8/11           10    10    11       3 |  0.508   0.438     0.333
    orange wall full by 10         14     9     3      10 |  0.555   0.328     0.684
    both, 8/11 + orange 10         14     8     4      10 |  0.570   0.320     0.727
    ridge floor 0.6                14    10    10       3 |  0.500   0.445     0.375
    ridge runs to 30               14    10     4       3 |  0.500   0.445     0.375
    ridge to 30 + floor 0.6        14    10     4       3 |  0.500   0.445     0.375

### Blocker 1 — the merge apron, and no fork knob touches it

`final[9..11]` loses **14 of 128 in six of the seven rows**. It is the single
largest site in every row, it does not move when the fork moves, and the one row
where it drops to 10 is the row that narrowed leg3's guard window rather than
anything at the merge.

This is specific to orange traffic. V1.9's 600-race blue benchmark lost 41 of
its 56 non-finishers to `leg2[99]` stalling and had `final` nowhere in the
picture. `MergeCatch`'s own docstring says why: blue arrives on its centreline
and goes straight down the sprint, while **orange crosses the apron** and is
returned by its fall after one wall. `MERGE_DESIGN_SPEED` is a single number,
41.0, and at 74–84% orange usage the apron is taking most of the field sideways.

The apron has to be rebuilt for orange volume. Not scanned — rebuilt.

### Blocker 2 — orange's lead is under-walled, and this one is tractable

Bringing orange's own west guard to full height sooner (`orange_window` 14 → 10)
is the only knob in the grid that does real work: escape **0.445 → 0.328**, blue
completion **0.375 → 0.684**, and leg3's own losses 10 → 3. Combined with the
narrower leg3 window it reaches finish 0.570, escape 0.320.

Still nowhere near production, and `all8` is 0.00 in all seven rows. But the
direction is real and it has not been exhausted.

## Dead hypotheses — do not re-scan these

**The ridge does not end too early.** The two channels part fast once the trim
releases: measured gap between leg3's east cradle edge and orange's west edge is
0.05 at step 8, **1.22 by step 11**, 2.88 by 15 and 4.88 by 20, against a 1.000
marble. `FORK_WINDOW_BLUE = 20` puts the ridge's end exactly where traces show
marbles free-falling out of `orange_lead[19..20]` at 90+ units per second, which
made "the ridge stops bridging them" the obvious reading.

It is wrong. Extending the ridge to 30 samples changes **where** marbles die —
`leg3[88]` disappears, `orange_lead[21]` and `leg3[99]` appear — and leaves the
totals byte-identical at 64 finished, 57 escaped, 7 stuck of 128. The ridge is a
*tent*, feet on both cradles and crest in the middle; lengthening it gives a
marble a longer ramp to run along and off, not a wall to be held by. `ForkRidge`
is load-bearing where the channels are close and cannot become containment where
they are far apart.

**`ForkRidge.CREST_FLOOR` does nothing measurable.** At 0.6 the results are
identical to the built course down to the loss-site counts, because
`MAX_FLANK * 0.5 * gap` outruns the floor within a couple of steps of the
release.

**Closing leg3's guard window earlier is nearly free of effect** on its own:
0.500 → 0.508 finish, and blue completion actually *falls* 0.375 → 0.333.

## The instrument that had to be fixed first, again

Sixth session running — see the `instrument-bugs-hide-geometry-findings` note.
Three separate things:

1. **The containment verdict had two tests and needed three.** A marble that
   falls through a gap between modules goes *down*: its `across` stays inside
   the half width all the way to the ground and its height never rises, so
   neither the lateral nor the vertical test fired. Over 24 seeds, 27 racers
   escaped and the escape tool located **none of them** — the whole of orange's
   loss was invisible to the one instrument built to explain it. `FLOOR_SLACK`
   is the third test and `lost_how` reports which fired.
2. **Finishers were booked as escapes.** The sprint's exit hands onto the finish
   deck, wider than the channel, so a racer rolling out past the line read as
   1.3 half widths outside `final[117]`. That was 43 of 90 recorded escapes over
   12 races, every one a racer who had already placed.
3. **A lateral test asks the wrong question at the fork**, because the other
   route's floor is there. 72 of 84 recorded escapes were on leg3 at samples 86
   to 91, every one east, every one with an eastward across-speed of 6 to 11
   units per second — not marbles leaving the course, marbles taking the other
   one. `SlopedRace._shared` excuses exactly those two flanks.

And a fourth, in the scan tool itself: **`ProcessPoolExecutor` reuses its
workers and the knobs are module attributes**, so a worker that had run a row
setting `orange_window` carried it into the next row that did not. The first
guards grid came back with its last three configurations byte-identical, because
they *were* the same configuration — and the one that looked best was the one
that had inherited another row's override. `_apply` now captures the defaults
once per worker and writes every knob on every job.

Three of the five scans in `docs/validation/sloped_race_v1/v110/` predate that
fix (04:04, 04:20, 04:31 against a 04:34 tool). `fork_lab_guards.json` has been
re-run and is the table above. The other two were dropped rather than re-run:
`fork_lab_crest` is superseded by `crest_height` and `crest_fine`, which sweep
the same single knob at finer spacing and post-date the fix, and
`fork_lab_control`'s only load-bearing row — the V1.9 geometry at 0.742 finish —
is independently corroborated by V1.9's own both-routes measurement.

**Provenance, stated because it is a gap.** The three escape counts in the list
above (27 located as none, 43 of 90 finishers, 72 of 84 on leg3) were read off
`escapes_before.json` and `escapes_trim.json`, which were produced *by the
broken verdict* and so cannot be regenerated now that it is fixed. Both files
were deleted during this session's cleanup, in error. The numbers survive here,
in the commit message for the verdict fix, and in the `SlopedRace._containment`
and `FLOOR_SLACK` docstrings, which is where this project keeps findings — but
the raw backing files are gone, and a future reader should treat those three
figures as quoted rather than re-checkable. `fork_trace_before.json` and
`validation_trace_blue.json` were kept and are intact.

## A render gap nobody has priced

`v2_track.gd` implements `guard_boost` and **nothing for `open_side`**. So the
opened wall has never been drawn, in any version.

On the shipped blue route this is latent. `MERGE_GUARD_WINDOW` opens *both*
sprint rails over `final[0..14]` — the apron's outer walls and roof are the
containment there — and the render draws them full height, but blue arrives on
its centreline and does not go where the difference is.

If orange ships it becomes visible immediately, and in the exact shape V1.9
warned about: a marble crossing to orange passes through a drawn full-height
guard, and blue marbles fly through orange's drawn overhang. Teaching
`v2_track.gd` `open_side` and `entry_trim`, and pinning both against the Python
the way `tests/test_sloped_guards.py` pins `GUARD_BOOSTS`, is a prerequisite for
any orange video — not a polish item.

## Tests

`tests/test_sloped_fork_trim.py`, 19 tests, all passing. The trim solve landing
on leg3's east cradle edge to `1e-9`; the clamp at the mouth; the self-release at
step 8 and that nothing overhangs past it; the section point count `sweep_rings`
requires; the skirt hanging below the seam and never on it; the crest window's
sixth entry, its easing, and its five-entry backward compatibility; that the
course installs `FORK_CREST`; and that the blue course opens no fork window and
builds no orange lead.

Also recorded there: the channels pass a marble diameter apart at step 11 while
the ridge runs to 20, so a future reader finds the gap arithmetic next to the
code rather than in this report alone.

## Where this leaves orange

Best measured forked configuration: **finish 0.570, all-eight 0.00, escape
0.320, orange completion 0.543 at 82% usage.** The brief asks for orange
completion >= 95% inside a 25–75% usage band.

Between here and there: the merge apron rebuilt for side-on volume, orange's
lead containment finished, and the renderer taught two geometry features. The
first is a redesign, not a scan.

Per sections 10 and 24 of the brief, this stops and reports rather than
continuing to scan. The trim is a genuine defect fix and is kept.

`FORK_CREST` is left at **0.05**, the open value the scan is indexed on, and
that is deliberate rather than a shipping choice: `routes="blue"` is the default
and does not build the fork, so the constant reaches nothing that ships, and
leaving it open keeps the both-routes course in the state the measurements above
describe. Anyone reading a both-routes race as production has misread it — at
0.05 that course finishes 50%. Closing the crest to 0.55 would make it a
99%-finish machine with one route unused, which is V1.9's position restated in
geometry; it is a one-constant change and is not made here, because whether
orange is abandoned is the decision this report exists to hand over.
