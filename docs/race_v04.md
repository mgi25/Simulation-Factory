# Race V0.4 — depth and doubt

V0.3 shipped a race that was technically correct and, watched, wrong in two
specific ways. The rendered Short looked like a board with coloured circles
sliding across it, and the winner was obvious long before the finish. This
phase is about those two problems and nothing else.

Both turned out to have measurable causes, and both were fixed by changing
what the course *is* and what the lens *sees* rather than by tuning numbers
until the output flattered. The evidence is below, and where a change did not
work it says so.

---

## How to run

```bash
# measure a course: predictability, fairness, comebacks, pack size
python -m tools.race_analysis --count 1200 --start-seed 20000 \
    --course machine --racers 16 --workers 10 --top 18

# check a course's geometry before running a single race
python -m tools.course_audit --all

# sweep the production camera and compare the same moments
python tools/race_camera_test.py output/race_v04/machine_20588_r16.json \
    --angles 45,50,55,60,74 --at 3.5,9,14,19,24 --out docs/validation/race_v04/camera

# draw the shape of a race, or two side by side
python -m tools.race_shape --race prototype:839271:10 --race machine:20588:16 \
    --out docs/validation/race_v04/shape_before_after.png

# render and encode
python race_main.py --seed 20588 --course machine --racers 16 \
    --export-replay output/race_v04/machine_20588_r16.json
python tools/render_replay.py output/race_v04/machine_20588_r16.json \
    --output output/race_v04/prod_20588 --race-camera production
python tools/encode_short.py output/race_v04/prod_20588 --silent
```

---

## Part 1 — measuring V0.3 first

Nothing was changed until the problem had a number. `race/analysis.py` runs a
race, samples the field twelve times a second, and reports what it saw;
`tools/race_analysis.py` does that across a batch in parallel. Two conventions
run through all of it:

* **Race progress** is a fraction of the *winner's* time. The race is decided
  when the winner crosses; the grace period afterwards is the pack coming home
  and belongs to no part of the question.
* **Course progress** is normalised to the course — 0.0 on the start plane,
  1.0 at the finish — so a gap is comparable between courses of different
  lengths.

**2 500 seeds of the V0.3 prototype, ten racers** (`docs/validation/race_v04/baseline_prototype_2500.txt`):

```
completions              2500/2500      failures 0    retirements 0
winner time              mean 16.87s    98.8% inside 15-22s
winner lock (fraction)   p10 0.05   median 0.69   p90 0.96   mean 0.62
                         locked before halfway 26.5%    at/after 75% 41.8%
leader at 10% wins       45.6%
leader at 25% wins       46.2%
leader at 50% wins       49.0%
leader at 75% wins       65.1%
competitive racers       10.00 / 7.06 / 4.95 / 3.86      (10%, 25%, 50%, 75%)
gap leader to median     0.024 / 0.074 / 0.123 / 0.142
lead changes             mean 5.14
winner worst rank        mean 3.02
final margin             mean 1.05s   median 0.88s
```

The leader at the quarter mark wins **46%** of the time, against a 10% base
rate. That is the complaint, stated as a number. And it does not decay: the
field is seven deep at 25%, five deep at halfway, and never recovers.

---

## Part 2 — the starting slot, which was the real scandal

V0.1 measured that every racer *id* could win, and concluded the race was
fair. It is not evidence. Ids are shuffled between grid slots by seed, so on a
course where the outside slot always won, every id would still win sometimes.

Counting the **physical slot** instead:

```
slot   starts   wins   win%    avg final   prog@25%   prog@50%
   0     2500     57    2.3%      6.51       0.109      0.352
   1     2500    122    4.9%      6.13       0.123      0.372
   2     2500    151    6.0%      6.11       0.125      0.366
   3     2500    508   20.3%      4.81       0.150      0.413
   4     2500    489   19.6%      4.66       0.159      0.424
   5     2500     65    2.6%      6.53       0.107      0.348
   6     2500    111    4.4%      6.23       0.119      0.363
   7     2500    138    5.5%      5.89       0.129      0.375
   8     2500    234    9.4%      5.58       0.139      0.390
   9     2500    625   25.0%      3.99       0.174      0.453
strongest slot 9 (25.0%)   weakest slot 0 (2.3%)   ratio 10.96x
```

Neutral is 10%. Three of the ten slots take 65% of the wins, and the spread in
progress at the quarter mark — 0.107 to 0.174 — says the advantage is real and
immediate rather than lucky.

The cause is structural and visible in one line of the prototype. Its opening
is a slick shelf from the left wall to x=820, and the grid's outermost column
is at x=920. Everything past the end of that shelf falls straight down while
everything on it has to roll the length of it first. Slots 4 and 9 are that
column; slot 3 is next to it.

**A shelf is the wrong instrument anywhere a starting field is above it.**
That single finding drove the whole opening redesign.

---

## Part 3 — the course, rebuilt around one rule

`race/courses/machine.py`. The design rule is:

> No advantage may survive more than one obstacle unchallenged.

Every stretch of travel is followed by something that either mixes the order
or closes the gaps, and the last of those sits at five sixths of the way down,
so the race is still being decided when the finish is on screen.

```
y        section     classification        what it is
      0  start       -                     4x5 staggered grid behind a gate
    700  spread      SPREAD                three peg rows, full width
   1180  bowl        MIX + COMPRESS        counter-rotors, basin, two drains
   2240  rapids      SPRINT                a slick roof and two catchers
   2920  lanes       CHOICE + RISK         divider: switchback / rotor
   3720  carousel    COMPRESS + MIX        a tray gate, then two scramblers
   4400  plunge      RISK                  kicker, platform, pit
   5370  sluice      COMPRESS + MIX        gated basin - the last compression
   5700  runin       CHAOS + SPRINT        plinko, a closing rotor, the chute
   6580  finish      -                     chute into a sloped paddock
```

Two of nine named sections are pure SPRINT; MIX and COMPRESS appear four times
each. `tests/test_race_analysis.py` asserts that classification so the course
cannot quietly become a corridor of sprints again.

### The three order-mixing mechanisms

**The mixing bowl** — a basin with *two* drains and an island between them.
The prototype proved that what congests a field is a floor rather than a
narrowing: racers arrive fast, lose it at the break in slope, then roll the
last stretch on track friction while the basin fills. That is copied
unchanged. What is new is the second hole: a racer arriving has to commit to
one side of the island, and which side is quicker depends on how many racers
are already leaning on it. Measured over ten seeds, the two drains take **51
and 49** racers.

**The tray gate** — a rotor whose hub sits exactly in the plane of a shelf,
with arms just long enough to reach the lips of the hole in it. Broadside, the
arms *are* the missing floor and the hole is shut; edge-on, the hub leaves a
passable gap either side. Racers pile on a closed gate and pour through
together when it opens. Nothing is teleported and nothing is queued by rule —
a racer four seconds ahead simply waits with the pack.

The hub is in the shelf plane rather than below it, and that is the safety
property the mechanism rests on: a rotor slung under the floor makes a pocket
between arm and shelf that a racer can be crushed in, and one at floor level
cannot, because there is no gap to be caught in.

**The lane split** — a peg on the centre line with a wall below it. Which side
of the peg a racer comes off decides which lane it takes: a grippy switchback
one side, a slick drop with a rotor in it the other. Measured over ten seeds,
the two lanes take **48 and 52** racers.

Neither lane is a branch in the progress graph. Both descend the same planes
over the same heights, so two racers level on the canvas are level in the race
whichever side they are on — what separates them is how long each side takes,
which is what a choice should cost.

### The opening

Three peg rows across the full width, on a lattice sitting on the *midpoints
between* the starting columns, with the grid cut from five columns to four so
that no column sits on the centre line.

Both of those are load-bearing and neither is decoration:

* A racer in free fall has no sideways velocity. A peg apex on a starting
  column's fall line is somewhere it can come to rest exactly on top of — and
  it did, twice a race in the first version, after which the recovery point
  (also on the centre line) dropped it back onto the same peg until it was
  retired. Ninety-five pixels off every fall line, there is no landing that is
  not a glancing one.
* Five columns put one on the centre line, and the centre line is where a
  symmetric course puts its splitter pegs. The fall line ran straight through
  the peg field and onto the apex of the bowl's island.

`race/audit.py` checks this as geometry rather than waiting for the outcome.

### What the redesign cost to find

Five failures were found by measurement, not by reading:

| what | how it showed up | fix |
|---|---|---|
| peg apex under a starting column | 2 racers a race stuck, then retired | lattice at the column midpoints |
| respawn on the same line as the peg | recovery dropped them back on it | respawn moved off the centre line |
| two shelves 40px apart | field wedged in a 60px gap, every seed | 80px step, 125px clearance |
| pit ending level with the basin | 6px slot, every pit racer rescued | 100px step down |
| shelves feeding the lane split | 100 of 100 racers went left | roof and catchers instead of shelves |

The last is the most interesting. Two long alternating shelves work exactly as
designed: a shelf gathers everything on it to its open end. Every racer left
the second one at x=260 and fell into the left lane, so the right lane and its
rotor were geometry nothing ever touched. A **roof** has no open end to gather
at — whichever side of the apex a racer lands, it leaves on that side.

### What did not work

The sluice was first built as a flat shelf with two tray gates on it, and it
did the opposite of its job. A gate on an open shelf only compresses when the
*leader* arrives at a shut one; the rest of the time the leader sails through
and the followers are held, which stretches the field. Rebuilt as a basin, the
constraint is the drain rather than the timing and the racer in front queues
like everyone else.

Then it was made too tight. At 145px of clear hole the basin passed racers one
at a time and stopped being a compression at all:

```
sluice hole   finished   final margin (median)   winner lock (median)
      145px    3.3/10                   3.02s                   0.86
      202px    8.5/10                   0.57s                   0.84
```

Three of ten reaching the line, and the first racer out of the gate winning by
three seconds, is a worse race than the one it replaced. Three abreast is wide
enough that a held-up pile leaves *together*, which is the whole point of
holding it up.

---

## Part 4 — the numbers, V0.3 against V0.4

1 200 seeds, machine course, sixteen racers, seeds 20000-21199
(`docs/validation/race_v04/machine_1200_r16.txt`). The V0.3 column is the
2 500-seed prototype baseline.

### Predictability

| | V0.3 | V0.4 | |
|---|---|---|---|
| winner lock, median | 0.69 | **0.92** | target >= 0.75, preferably >= 0.80 |
| winner lock, mean | 0.62 | **0.80** | |
| winner lock, p10 | 0.05 | **0.40** | |
| winner lock, p90 | 0.96 | 0.97 | |
| locked before halfway | 26.5% | **13.7%** | |
| locked at/after 75% | 41.8% | **71.6%** | |
| leader at 10% wins | 45.6% | **10.5%** | |
| leader at 25% wins | 46.2% | **15.4%** | |
| leader at 50% wins | 49.0% | **33.4%** | |
| leader at 75% wins | 65.1% | **40.6%** | |

The leader at the quarter mark went from a near coin-flip predictor to barely
better than the field. At halfway it is still wrong two times in three.

### Pack and comebacks

| | V0.3 (of 10) | V0.4 (of 16) | V0.4 as a share |
|---|---|---|---|
| competitive at 10% | 10.00 | 15.90 | 99% |
| competitive at 25% | 7.06 (71%) | 14.65 | **92%** |
| competitive at 50% | 4.95 (50%) | 13.19 | **82%** |
| competitive at 75% | 3.86 (39%) | 4.20 | 26% |
| gap leader to median at 50% | 0.123 | **0.062** | |
| lead changes | 5.14 | **10.71** | |
| distinct podium racers | 7.80 (78%) | 11.69 (73%) | |
| winner's worst rank after 25% | 3.02 | **7.68** | |
| final margin, median | 0.88s | **0.49s** | |
| overtakes, first/middle/final third | 49/18/22 | 215/138/75 | |

"Competitive" is racers within a tenth of the course of the leader. At halfway
V0.4 still has 82% of the field in that band where V0.3 had half. The one
metric that did *not* improve is competitive at 75% — see known problems.

### Fairness

```
slot   starts   wins   win%    prog@25%      slot   starts   wins   win%    prog@25%
   0     1200     40    3.3%      0.254         8     1200     61    5.1%      0.265
   1     1200     84    7.0%      0.267         9     1200    111    9.2%      0.274
   2     1200     79    6.6%      0.260        10     1200    103    8.6%      0.273
   3     1200     83    6.9%      0.259        11     1200     68    5.7%      0.261
   4     1200     55    4.6%      0.258        12     1200     49    4.1%      0.262
   5     1200     89    7.4%      0.273        13     1200     70    5.8%      0.257
   6     1200     81    6.8%      0.265        14     1200     89    7.4%      0.276
   7     1200     79    6.6%      0.264        15     1200     59    4.9%      0.254
strongest slot 9 (9.2%)   weakest slot 0 (3.3%)   ratio 2.77x   (neutral 6.25%)
```

| | V0.3 | V0.4 |
|---|---|---|
| strongest / weakest win rate | 10.96x | **2.77x** |
| range of progress at 25% | 0.107 - 0.174 (63% spread) | 0.254 - 0.276 (**9% spread**) |

The progress spread is the honest measure of the structural advantage, and it
has essentially gone: every slot is at the same place a quarter of the way in,
to within a percent of the course. What remains in the win rate is smaller and
is documented below as a known problem.

One fairness bug was found and fixed during this phase. The bowl's two intake
rotors were originally staggered in height so their sweeps could overlap in x
without the arms reaching each other. Over 1 200 races the leftmost starting
column won 4.3% against about 7% for the other three, because the column
nearest the higher rotor met it sooner and slower. Levelling them — and cutting
the reach from 195 to 185 so the circles clear at the same height — took the
ratio from 3.35x to 2.77x. **A mirror-symmetric course has to be symmetric in
time as well as in space.**

---

## Part 5 — how many racers

400 seeds each on the final course (`docs/validation/race_v04/machine_400_r*.txt`).

| | 10 | 16 | 20 |
|---|---|---|---|
| failures / retirements | 1 / 1 | **0 / 0** | 1 / 1 |
| recoveries per race | 0.18 | 0.49 | 1.04 |
| winner time, mean | 17.03s | 16.79s | 16.76s |
| field home inside the window | 84% | 73% | 65% |
| winner lock, median | 0.90 | **0.92** | 0.92 |
| locked before halfway | 18.0% | **11.8%** | 17.0% |
| leader at 25% wins | 17.0% | **13.5%** | 16.8% |
| leader at 50% wins | 40.8% | 35.0% | **34.0%** |
| competitive at 50%, as a share | 87% | 84% | 77% |
| winner's worst rank | 5.58 | 7.62 | **7.98** |
| slot ratio | 1.72x | 2.69x | 3.20x |

**Sixteen.** Not because it wins every column - twenty is marginally better on
comebacks and on the leader at halfway - but because:

* it is the only count with no failure and no retirement in 400 races, and it
  repeated that over the 1 200-seed acceptance batch;
* it has the lowest early lock (11.8%) and the weakest early leader (13.5%);
* 73% of the field is home inside the finishing window against 65% at twenty,
  and the results table is most of the payoff;
* recoveries run at half the rate of twenty;
* and there are exactly sixteen racer colours a viewer can tell apart at
  Shorts scale. At twenty, four pairs of racers are the same colour, and a
  number plate is not enough to separate two red balls in a pile-up.

The slot ratio looks best at ten, but that is partly an artefact of counting:
fewer slots means more starts each and a smaller relative spread. The
progress-at-25% spread, which does not have that problem, is flat at all three
counts.

---

## Part 6 — the camera

`tools/race_camera_test.py` renders the same five moments of one replay at
five elevations through one build of one scene, so the only difference between
two frames of the same name is the lens. The elevation is passed to Godot at
render time (`--race-elevation=`) rather than edited into the constant, for
exactly that reason.

Stills: `docs/validation/race_v04/camera/e{45,50,55,60,74}/`.

| angle | what the frame does |
|---|---|
| 45 | most depth of any candidate, and too far back: the derived camera distance grows as the lens drops, and at sixteen racers the number plates start colliding in a pack |
| 50 | strong depth, plates legible but small |
| **52** | **chosen.** the lowest angle at which a sixteen-plate field stays comfortably readable, with the side faces of every beam still visible |
| 55 | plates larger, beam faces beginning to foreshorten |
| 60 | clearly perspective, but the machine is flattening |
| 74 | V0.3. every vertical surface edge-on, nothing occludes anything - a plan view whatever the projection says |

74 degrees was not an arbitrary choice in V0.3 and the argument for it was
sound: a course six times longer than it is wide only gets its height back by
looking down the length of it. The argument is still true. It is simply
outweighed, because a viewer cannot see that a machine has levels from
directly above it.

---

## Part 7 — the machine, drawn

The authoritative physics is still 2D pymunk. Nothing below changes a
simulation number; all of it is a mapping from the course the solver used onto
a machine a viewer can read.

### The deck

Every piece of this course lies in one plane, and the only reason the render
has a vertical axis at all is that nothing in the simulation uses it. So it is
spent on the one thing a flat course cannot show: that a marble machine is a
stack of levels, and that a racer moving down the course is descending through
it.

`_deck(sim_y)` is a single monotone function of course height, stepping down
once per named section, smoothed across a 300px window so nothing pops. It is
applied to **everything** — pieces, spinners, racers, trails, effects and the
camera's aim — through the one `to_world()` that all of them already went
through. That is what makes it truthful:

* two things at the same point on the course are at the same visual height, so
  a racer can never appear sunk into a ramp it is really resting on;
* the function only ever decreases, so visual descent and course progress mean
  the same thing.

A long piece is cut along its own length into segments short enough to take
the deck at their own midpoint, and each segment is tilted to meet its
neighbours. A short piece is one segment and costs nothing; a boundary wall is
thirty and follows the machine down.

The deck is invisible to the verification camera, which is orthographic and
points straight down: screen position there depends on X and Z only.

### Depth from the data, not from a list of names

The replay describes every piece as a bar with an angle, and that is all the
scene uses. A near-vertical bar is a face of the machine and is drawn as one;
a near-flat bar is something racers run along and is drawn as a deck:

```
BEAM_HEIGHT        0.62    a flat platform          (V0.3: 0.30 for everything)
BEAM_WALL_HEIGHT   1.55    a vertical face
WALL_HEIGHT        2.30    the course boundary      (V0.3: 1.35)
PEG_HEIGHT         0.98    a post, with a base      (V0.3: 0.62)
```

A racer's radius is 0.30 units, so a V0.3 ramp was exactly one racer radius
deep — invisible at 74 degrees and the reason the course read as markings on a
floor. Nothing here knows what a funnel is, which is why the bowl's walls come
out tall (they are steep), the shelves come out as decks (they lie flat), and
the prototype and split courses get the same treatment for free.

Beams are hung *below* the deck line rather than standing on it: a racer runs
along the top of a simulation bar, so the top of the drawn beam is where the
bar is and all the added depth is underneath, where it cannot lift a racer off
its surface. Platforms longer than 2.2 units get posts under them, which is the
single most effective depth cue in the frame after the deck itself — a slab
with air and a shadow beneath it is unmistakably an object where the same slab
flat on a floor is a marking.

### Parallax

Three ranks of scenery at three distances, which is what gives the eye a
*comparison* rather than just a rate: recessed rails let into the deck itself,
structural ribs on the course walls at a 4.0-unit pitch, and a taller rank
further out at 7.0. At 52 degrees the near rank crosses the frame in roughly
half the time the far one takes.

The deck rails run *along* the course, not across it. Anything drawn across
the track reads as a rung and puts the frame straight back into diagram
territory.

### What was removed

The brief's "board-like elements", and each was a real thing in the V0.3
frame:

* **Checkpoint bars.** V0.3 drew a lit bar the full width of the course at
  every progress plane — a dozen horizontal lines down the frame. Production
  now gets two short studs let into the deck at the edges of the plane. The
  full bar survives on the measuring lens, where there is nobody to mislead.
* **Section gantries.** A first attempt marked each boundary with two posts
  and a lit beam across the top. Nine boundaries, nine more rungs. The beam is
  gone; the posts remain and carry the zone light vertically instead.
* **Step faces.** The riser that makes a level change legible was first drawn
  across the whole width. It read as another rung *and* stood between the lens
  and the racer arriving at it. It is now two wings from the walls inwards,
  with the racing line left open.

### Zones

One two-colour ramp — cool at the top of the course, warm at the bottom, on
the gantry posts only. It says "you are further along" and nothing else.

---

## Part 8 — effects

An effect exists to say *something happened to that racer*. The moment it is
large enough to hide the racer, it has stopped saying that. So the tiers are
set against the ball, whose radius is 0.30 units:

| | V0.3 | V0.4 | as racer radii |
|---|---|---|---|
| ordinary collision ring | 0.62 | 0.45 | 2.1 -> **1.5** |
| hard collision ring | 1.55 | 1.10 | 5.2 -> **3.7** |
| jump ring | 0.95 | 0.70 | 3.2 -> 2.3 |
| the win | 3.20 | 2.40 | 10.7 -> 8.0 |
| spark overdrive | 2.6 | 1.7 | |
| ring alpha | 0.95 | 0.72 | |
| camera shake, max | 0.055 | 0.040 | |

On a 1080-wide frame a 5.2-radius ring is 310 pixels of additive white across
a third of the course, several times a second in a pile-up, and it was
routinely the brightest thing in a shot where the brightest thing should be a
racer. `tests/test_race_visuals.py` holds the ratios so they cannot drift back
up.

---

## Part 9 — the measuring lens, which turned out to be lying

The verification camera exists so a render can be proven to be the race the
simulation ran: `verify_race_render.py` takes a racer's recorded position,
subtracts the camera track, and looks for the racer's colour at that pixel.
Its whole premise is that a flat unshaded racer reaches the file as the colour
the replay names.

It did not. ACES tone mapping is applied to the whole frame, unshaded surfaces
included, and racer 7's `(72, 226, 224)` arrived in the PNG as
`(157, 230, 228)`. The hue survived, which is why the check worked at all, but
cyan had drifted far enough that the racer was lost whenever a neighbour
covered part of it.

That was true in V0.3 as well — rendering the same frame from both trees gives
byte-identical racer colours. It only became visible because V0.4 sampled
thirty frames rather than twenty-four.

Three things were fixed on the measuring lens, none of which touch the
production camera:

* **Linear tone mapping.** A tone curve is a deliberate distortion of colour,
  which is exactly what a production frame wants and exactly what a
  measurement must not have.
* **Nothing may stand over the track.** Gantry posts, pinch gates and finish
  posts are several times a racer's height and sit at the course edges; from
  directly above they cover the lane a racer hugging the wall is in. They are
  presentation, so they are off.
* **Everything else is flattened** to 0.16 units, well under a racer's centre
  at 0.30, so no rotor arm or peg can win the depth test against the thing
  being measured.

Result, `prototype_839271`, thirty sampled frames:

```
                        V0.3 render        V0.4 render
positions measured      205                205
located                 204  (missing 1)   205  (missing 0)
position error mean     1.19px             1.12px
              median    0.74px             0.76px
              95th      5.21px             3.41px
              worst    11.06px            11.24px   (fails above 16px)
silhouette ratio        1.03x              1.03x
OK: every sampled racer is where the replay put it
```

The camera itself — orthographic, straight down, one simulation pixel to one
frame pixel — is unchanged, and `tests/test_race_visuals.py` asserts it.

---

## Part 10 — the course audit

`race/audit.py` and `tools/course_audit.py`. Five static checks on geometry,
run before a single race, each corresponding to a way a course actually broke
during this phase: respawn clearance, pinch traps, rotor sweeps against
geometry, rotor sweeps against each other, and balance points under a starting
slot. It is arithmetic on the same `corners()` the solver builds its polygons
from, so a finding is a fact about the course rather than a guess.

All three shipped courses report zero errors. `tests/test_race_analysis.py`
asserts that, and asserts that the check fails on a deliberately broken
course.

---

## Part 11 — candidates, and watching them

Three seeds were shortlisted from the 1 200-seed batch by a blunt score (late
lock, a big pack at halfway, a comeback, podium turnover, a close finish, a
winner time in band) and then watched. This is not the curation system —
Part 30 of the brief rules that out for now — it is a shortlist for a human.

| | 20588 | 20529 | 20645 |
|---|---|---|---|
| winner | Racer_02, slot 2 | Racer_10, slot 6 | Racer_02, slot 7 |
| winner time | 16.73s | 17.08s | 17.60s |
| winner lock | 0.98 | 0.98 | 0.98 |
| lead changes | 13 | 20 | 13 |
| winner's worst rank | 16th | 16th | 16th |
| distinct podium racers | 15 | 15 | 13 |
| final margin | 0.15s | 0.29s | 0.07s |
| competitive at 10/25/50/75% | 15/15/16/8 | 16/16/16/8 | 16/16/16/2 |
| winner's rank at 10/25/50/75% | 15/16/9/5 | 12/16/12/2 | 16/16/14/10 |

Ten stills each, one per section, in `docs/validation/race_v04/moments_*/`.

### The watch test, answered honestly for 20588

1. **Can the winner be guessed by 25%?** No. Racer_02 is 16th at the quarter
   mark. Sixteen racers are inside a tenth of the course of the leader.
2. **By 50%?** No. It is 9th, and the whole field is still competitive.
3. **Are multiple racers relevant near 75%?** Yes, but fewer — eight are
   within the band and the winner is 5th. This is the weakest part of the
   race and it is the same weakness the batch reports.
4. **Obvious comeback moments?** Yes: last to fifth across the carousel and
   the plunge, then fifth to first through the sluice and the run-in.
5. **Do random paused frames look three-dimensional?** Yes. Every still has
   foreground ribs, mid-ground beams with visible side faces and posts under
   them, and a background that recedes into fog. The bowl reads as a bowl.
6. **Any long boring section?** No. The leader's pacing, averaged over
   sixteen seeds, is below - no section runs longer than 2.9 seconds, and
   every one of them has at least one obstacle in it. The quietest stretch is
   the rapids at 1.9s, which is four slick surfaces and nothing else, and it
   is there on purpose.

   ```
   spread    0.96s    lanes       2.84s    plunge exit   2.14s
   bowl      1.65s    carousel    2.17s    sluice        1.65s
   rapids    1.86s    plunge      0.70s    run-in        2.89s
   ```
7. **Does any effect obscure the race?** No. The largest thing in the finish
   still is a racer.
8. **Does the ending have tension?** Yes. Four racers cross within 0.4s, the
   winner having taken the lead inside the last half second.

**Selected: seed 20588.** It has the latest lock of the three that also lands
inside the target winner time, the winner comes from dead last, fifteen of
sixteen racers hold a podium place at some point, and the finish is a
four-way. 20529 has more lead changes but its winner is second for most of the
closing stretch, which reads as less of a comeback; 20645 has the closest
margin but only two racers are still in contention at 75%.

---

## Part 12 — before and after

### The shape of a race

`docs/validation/race_v04/shape_before_after.png` — the V0.3 shipped seed
beside two V0.4 candidates. Four charts each: who led, the winner's rank over
time, pack spread, and how many racers were competitive.

The V0.3 panel is two wide bands of colour with a flat line under them: one
racer takes the front early and the picture stops changing. The V0.4 panels
are striped, and the winner's line dives to the bottom of the chart before
climbing.

### The frame

| moment | V0.3 (74 degrees, flat pieces) | V0.4 (52 degrees, machine) |
|---|---|---|
| start | `docs/validation/race_v03/after/v03_839271_start.png` | `docs/validation/race_v04/moments_20588/v04_20588_start.png` |
| early mixer | `.../v03_839271_spinners.png` | `.../v04_20588_bowl.png` |
| middle | `.../v03_839271_funnel.png` | `.../v04_20588_lanes.png` |
| late | `.../v03_839271_jump.png` | `.../v04_20588_sluice.png` |
| finish | `.../v03_839271_finish_line.png` | `.../v04_20588_finish_line.png` |

---

## Part 13 — the final video

```
output/race_v04/prod_20588/short.mp4
1080x1920, 60fps, h264 High, yuv420p, 1683 frames, no audio track
28.05s, 35.9 MiB, from 1013 MiB of PNG
```

Also produced: `prod_20529/short.mp4` (28.40s) and `prod_20645/short.mp4`
(28.92s).

---

## Known problems

**The Short is 28.1 seconds, against a preferred 18-25.** The winner's time is
16.7s and inside the 15-22s target; the overshoot is the 6.5-second finishing
grace, which is a shared constant and is what brings the pack home after the
winner. Shortening it was measured rather than assumed:

```
grace   field home    duration   Short
 6.5s    11.9/16        23.3s    28.1s
 5.0s     9.8/16        21.8s    26.6s
 4.0s     7.8/16        20.8s    25.6s
 3.5s     6.1/16        20.3s    25.1s
```

Losing half the field from the results table to save 2.5 seconds is a worse
race, and the finish is most of the payoff. It was left alone. The right fix
is a trim that ends the Short a fixed time after the winner crosses — a
presentation decision that belongs with the curation pipeline the brief
defers, not with the course or the physics.

**Competitive racers at 75% is 4.2 of 16**, and it is the one pack metric that
did not improve. The field is genuinely strung out between the carousel and
the sluice: the plunge's pit is a long detour, and a tray gate that the leader
happens to arrive at while it is open stretches the field rather than closing
it. The sluice puts four or five racers back on level terms, which is what
makes the ending work, but it does not gather the tail. A third compression
between the carousel and the plunge would probably fix it and would cost
around two seconds of race time this course does not have.

**Residual starting-slot bias, 2.77x.** Down from 10.96x, and the structural
part is gone — every slot is at the same course progress at the quarter mark
to within a percent. What remains is a mild penalty for the outer grid
columns: grouped by column, the win rates are 4.3%, 7.4%, 7.4% and 6.0%
against a neutral 6.25%, and the leftmost is about five standard errors low
over 1 200 races. The likeliest cause is the pre-start pack: sixteen racers on
a 1 000px gate are shoulder to shoulder, the outermost end up against the
walls, and the edge channel through the peg field is 88px wide against 126 in
the interior. Not chased further this phase.

**One racer in a thousand still needs rescuing more than once.** 636
recoveries in 1 200 races of sixteen, zero retirements, zero timeouts. The
tray gates account for most of it — a racer riding an arm as it tips is
briefly slow and making no progress, which is what the stuck detector looks
for.

**The rapids is the least interesting 1.9 seconds of the course.** It is there
because a course made only of mixers is a lottery rather than a race, and a
viewer needs somewhere to see that a racer is quick. It does that job and
nothing more.

---

## What is kept under `docs/validation/race_v04/`

The four `.txt` reports carry every number quoted above. The raw per-race JSON
each of them was written alongside is **not** committed - it runs to 13 MiB and
is exactly reproducible from the commands at the top of this file, all of which
name their seeds.

Of the images, a subset:

* `camera/e{45,50,55,60,74}/still_{000210,000840,001440}.png` - three moments
  at five elevations, the artefact the camera decision was made from.
* `moments_20588/` - all ten sections of the selected race.
* `moments_20529/`, `moments_20645/` - start, bowl, lanes, plunge, sluice and
  finish for the two candidates that were not chosen.
* `shape_before_after.png` - the race-shape charts.

---

## Tests

`1063 passed`, up from 1010. New in this phase:

* `tests/test_race_analysis.py` — 36 tests. Every metric is checked against a
  trace built by hand, where the right answer is known by construction: a
  winner-lock computation that only agreed with itself would be no use.
  Covers winner lock (including the two edge cases: leading from the start,
  and taking the lead by crossing the line), lead changes, top-3 turnover,
  the comeback metric, overtakes by thirds, progress sampling, pack spread,
  competitive count, slot statistics, the audit's five checks, and the
  machine course's classification and opening rule.
* `tests/test_race_visuals.py` — 17 more. The production camera's elevation
  band, the elevation override, beam depth, angle-derived heights, the deck's
  monotonicity and its application through `to_world`, the measuring lens's
  guarantee, no checkpoint bar or gantry beam across the track in production,
  the VFX ratios against the racer's radius, two rib ranks at different
  distances, struts, and the room's overrun.

Determinism, the verification camera, and battle rendering are all asserted by
tests that existed before this phase and were not touched.

---

## What did not change

`race/manager.py`, `race/simulation.py`, `race/racer.py`, `race/progress.py`,
`race/course.py`, `race/runtime.py`, `race/camera.py`, `race/telemetry.py`,
`race/seeds.py`, the prototype and split courses, the replay schema, and every
file under `engine/`, `modes/`, `powers/` and `entities/`. The fight system is
untouched. `race/config.py` changed in one place: six more racer colours, all
appended after the existing ten.
