# Two blockers that did not fall, and what the measurements say instead

V1.2 was asked to solve three things. One is solved and closed; the other two
resisted, and this is the evidence rather than an apology. Both are recorded
here at the level of detail the next attempt needs, because in each case the
useful output of this session is a *mechanism* rather than a knob.

`docs/sloped_race_v12.md` has the shipped numbers.

---

## 1. The start: the convergence has to happen somewhere

### What was asked

Stop tuning inside the funnel; change the local start architecture to

    visible 8-bay start -> short equal launch -> WIDE SHALLOW MIXING TRAY
    -> physical interactions while several marbles remain abreast
    -> only then gradual narrowing

That is exactly what was built, twice, in two different places. Both are worse
than the funnel they replaced.

### The tray in the fan: three geometries, all worse

`StartGrid.tray` replaces the single 7.34-unit taper with converge-hold-narrow,
and `deflectors` puts rounded bumpers in the held stretch. Over 300 seeds each,
against V1.1's rank span of 3.77 places:

| candidate | rank span | trailing |
|---|---|---|
| V1.1 (`wheel-s32-r9`) | **3.44** | 0.5% |
| tray, no bumpers | 6.04 | 0.8% |
| tray + 2x2 bumpers | 7.00 | 69% |
| tray + 2-1-2 bumpers | 6.60 | 75% |
| tray + 2-1-2, low | 6.56 | 70% |
| tray + 2-1-2, fat | 6.50 | 75% |
| wider tray + 2-1-2 | 6.82 | 62% |

Two separate failures, and the first is the more interesting.

**A plain wide tray makes the bias *cleaner and stronger*.** Its slot means
came out

    7.38  5.67  4.01  1.85  1.34  3.25  5.19  7.32

which is a clean symmetric V - the bias in its purest form. Holding the trough
wide for longer does not un-order anything; it just shortens the stretch the
narrowing has to happen in, so the narrowing is sharper and the outer bays pay
more. The funnel was never the *cause*; the cause is that lateral position at
the funnel is a perfect function of bay index, and a wide tray with nothing
stirring in it does not change that.

**Bumpers in the fan jam it, and the reason is energy, not shape.** The fan
falls 0.63 layout units over 7.34 - 4.9 degrees overall. Spend the drop needed
to get the field moving before the tray and the drop needed to feed the launch
after it, and what is left across the tray is **1.72 degrees**. Rolling
friction is zero so a marble still accelerates, but a marble that loses speed
on a bumper at 1.7 degrees never gets it back, and two thirds to three quarters
of the field is still on the deck when the leader has gone.

### The mixing stretch on the launch: same answer, louder

The launch runs at 25 to 43 degrees, so `TrackRun.width_profile` opens it out,
the fan holds its width to the seam and hands over at the wider mouth, and the
mixing stretch and the convergence both happen where there is energy to spend.

| candidate | opening | rank span | lost | trailing |
|---|---|---|---|---|
| V1.1 | - | **3.38** | 0.9% | 0.5% |
| launch 1.55x, mixed | samples 30-96 | 6.23 | 4.4% | 64% |
| launch 1.55x, plain | samples 30-96 | 5.93 | 12.7% | 69% |
| launch 1.85x, mixed | samples 34-100 | 5.44 | 6.7% | 27% |
| launch 2.20x, plain | samples 26-62 | 5.75 | 34% | 28% |

The losses are **not** in the wide stretch. They are at `launch[70..100]`,
*after* the convergence: a wide fast field squeezed back to 1.88 is thrown
sideways and leaves where the launch banks into its first turn.

### The finding

Eight bays 4.4 units across have to become one channel 1.88 wide. **The
convergence has to happen somewhere, and wherever it is put it does one of two
things:**

* **slowly**, in the start deck, where there are 0.63 units of drop - and it
  *orders* the field, because at 8 to 11 wu/s the marble that reaches the line
  first is the one with least distance to travel;
* **quickly**, on the launch, at 25 to 43 degrees - and it *ejects* the field,
  because the same lateral squeeze at 35 wu/s puts marbles over the wall.

A mixing region only decorrelates if marbles keep enough speed to be scattered
rather than queued, and the only stretch with that much energy is the one whose
convergence throws them out. That is a property of the frozen macro layout -
the start deck's height above the launch entry - and not of any shape tried
inside it.

**Twenty geometries have now been scanned across two sessions** - stagger, fin
schedules, merge trees, three densities of thin deflector, six wheel positions
and rates, three trays, five bumper sets and four launch openings. The only one
that ever reduced the span did it by holding a fifth of the field up.

### What would actually be needed

More drop in the start deck, which means moving `NODES["start"]` up or the
launch entry down - a macro-layout change, and out of scope by the brief's own
first line. Failing that, the honest statement is that this course's start is a
seeding mechanism and not a fair one, and the race is entertaining anyway
(section 4 of the shipped report).

---

## 2. The fork: the guard that must open is the wall the field leans on

### The trade, measured

Orange is reached across leg3's east guard, which is opened over a window of
samples past the fork. Twelve seeds of eight per row:

| leg3's east guard | finish | escape | blue / orange |
|---|---|---|---|
| **shut** | **0.979** | 0.021 | 94 / 0 |
| open 4 samples | 0.396 | 0.604 | 93 / 1 |
| open 5 samples | 0.240 | 0.740 | 93 / 1 |
| open 6 samples | 0.260 | 0.698 | 77 / 17 |
| open 7 samples | 0.323 | 0.625 | 61 / 33 |
| open 9 samples | 0.323 | 0.625 | 43 / 51 |
| open 12 samples (V1.1) | 0.312 | 0.635 | 40 / 54 |

**Route usage is not the problem.** At the shipped window both routes get real
traffic - 43/57 - which is inside section F's 25-75% band. Reliability is the
problem, and it is not a tuning question: every open window loses two thirds of
the field, and shutting it recovers 98%.

### It is not the ridge, and not orange's own guard

Both were eliminated by direct test rather than by argument:

* **ForkRidge removed entirely**: finish 0.323 against 0.312. No effect.
* **Orange's west guard held open longer** (samples 14 -> 20, 28, 36, 44):
  finish *falls* 0.312 -> 0.250 -> 0.156 -> 0.135 -> 0.083. It is containing,
  not obstructing.
* **leg3's guard never opened**, everything else built: finish **0.979**,
  escape 0.021, one loss site in twelve seeds. Orange's lead and lobe colliders
  are present and harmless.

So the ejector is the opening itself.

### Why the opening cannot be made safe here

leg3's tail turns 38 degrees right over 2.3 units and is banked **26 degrees**,
which `min_radius_layout` says is 1.7 degrees more than a marble at 43 wu/s
needs to hold that radius - so the bank is a requirement, and it presses the
whole field against the east wall. The branch is on the outside of that turn.
The wall that has to open is the one the field is leaning on.

A marble crossing it must land on orange's floor immediately, and it does not.
Measured in world height across the seam:

| leg3 sample | orange's floor at leg3's east lip | horizontal gap |
|---|---|---|
| 84 | 0.656 below | 0.12 |
| 88 | 0.767 below | 0.03 |
| 90 | 0.709 below | 0.54 |
| 92 | no surface within 1.5 | - |

V1.1 corrected orange's lead for **roll** (it now starts at leg3's own 26
degrees) and for **elevation along its centreline** (`_held_heights` holds
leg3's gradient over the overlap). Both were necessary and neither is
sufficient, because the mouth is at leg3's **east lip**, not its centreline,
and the lip's height is the centreline plus the bank times the half width -
which changes as leg3's width and bank change through the tail.

### What the next attempt should do

Derive orange's lead height from **leg3's east lip trajectory** rather than its
centreline: sample `leg3.surface_point(s, +CHANNEL_HALF)` through the crossing
window and make the lead's floor follow *that* curve for as long as the guard is
open. If the two surfaces are continuous at the lip, a marble pressed against
the opened wall rolls onto orange instead of off the course, and the window can
be as wide as the route balance wants.

That is a bounded, checkable change - the seam probe in this session's
scratchpad measures exactly the quantity it has to drive to zero - and it is
where a third session should start.

### What ships meanwhile

`routes="blue"`. Not because the fork is abandoned - its geometry, its entry
test and this measurement all stay in the tree - but because a two-route race
that finishes 31% of its marbles is not a race.
