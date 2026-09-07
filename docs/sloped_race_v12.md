# The sloped race, V1.2

One of the three blockers is closed and the course is now reliable. The other
two are not closed, and `docs/sloped_race_v12_findings.md` is the evidence for
why - in both cases a mechanism rather than a missing tuning pass.

Numbers quoted from V1 and V1.1 are labelled. V1's were taken on a course whose
merge trapped marbles and whose orange route was unreachable; V1.1's on one
whose merge apron still lay across blue's channel. Neither is a like-for-like
comparison and both are given only to show direction.

---

## 1. Reliability - closed

600 seeds, 4800 racers, 32-second window at 240 Hz, `routes="blue"`.

| | V1 | V1.1 | **V1.2** |
|---|---|---|---|
| finished | 84.35% | 91.96% | **97.69%** |
| escaped | 8.33% | 1.12% | **1.23%** |
| stopped in the machine | 7.31% | 6.92% | **1.08%** |
| all eight finished | 26.8% | 54.0% | **82.3%** |

| finishers | 8 | 7 | 6 | 5 |
|---|---|---|---|---|
| races | **494** | 102 | 3 | 1 |

Against section G's targets - 98% per racer, 90% all-eight - this is 97.7% and
82.3%. Close, and not there. What is there is that **no race loses more than
three marbles** where V1 lost a whole field in one seed, and the stopped rate
has fallen by a factor of seven.

### The trap that did it

`blue[100..119]` took 285 of V1.1's 384 losses, and six marbles came to rest at
the same coordinates to two decimals. It was a step, and the step was
arithmetic: `MergeCatch._floor` built the apron upstream of the sprint on the
chord to blue's mouth - falling 0.159 per unit - and then continued on that
same line past blue's mouth, where blue's own channel falls at 0.200. Over the
2.1 units between them the apron rose into a shelf across blue's channel,
+0.114 simulation units at its back edge. A marble needs 7.5 wu/s to climb
that. The fast ones never noticed; the slow ones stopped dead.

Past blue's mouth the apron now follows blue's own gradient. The shelf is
+0.034, and what is left is blue's centreline riding the sprint cradle's wall -
a curved surface, not a lip.

`tools/sloped_merge_test.py` is the section D test. Run against the old
geometry it finds `blue[112]` three times over; against the new one, 35 of 35
entries finish, at speeds down to 8 wu/s.

### Where the remaining 111 losses are

| site | losses | what is there |
|---|---|---|
| `leg2[80..99]` | 52 | the spinner corridor |
| `leg1[80..99]` | 32 | leg1's tail into the second hairpin |
| `leg1[40..79]` | 15 | leg1's body |
| everything else | 12 | |
| `blue[100..119]` | **1** | was 285 |

The two hotspots are now the obstacle and the hairpin before it - places where
the course is *supposed* to be hard. Section G says to fix only concentrated
hotspots and not to retune physics globally; at 52 and 32 out of 4800 these are
the next candidates rather than defects.

---

## 2. The start - not closed, and now understood

**Slot win ratio 18.42**, against V1.1's 8.99 and a target of 2.5.

| bay | win | podium | finish | rank at 9% | at 50% | at 75% | finish rank |
|---|---|---|---|---|---|---|---|
| 0 | 1.33% | 20.0% | 97.3% | 6.24 | 5.43 | 5.41 | 5.32 |
| 1 | 6.33% | 33.5% | 98.7% | 5.13 | 4.72 | 4.75 | 4.70 |
| 2 | **24.50%** | 50.5% | 97.0% | **2.91** | 3.69 | 3.81 | 3.70 |
| 3 | 15.67% | 38.7% | 97.5% | 4.61 | 4.45 | 4.42 | 4.34 |
| 4 | 18.33% | 43.3% | 96.3% | 3.81 | 4.13 | 4.20 | 4.07 |
| 5 | 11.67% | 32.0% | 98.0% | 4.86 | 4.82 | 4.72 | 4.65 |
| 6 | 16.17% | 46.5% | 98.2% | 3.65 | 4.08 | 4.05 | 3.99 |
| 7 | 6.00% | 35.5% | 98.5% | 4.80 | 4.68 | 4.63 | 4.57 |

Spearman, bay against finish rank: **−0.075**.

**The ratio got worse because the course got more reliable, and that is worth
being explicit about rather than hiding.** V1.1 removed 8% of its field more or
less at random, and a marble removed at random is a win taken from whichever
bay it belonged to - noise that flattened the win rates. With 97.7% finishing,
what is left is the bias on its own. The *rank* columns barely moved: bay 0 was
6.20 at the 9% checkpoint in V1.1 and is 6.24 now. Nothing about the start got
worse; the measurement got cleaner.

Why it was not fixed is in the findings note, and the short version is that
eight bays 4.4 units across have to become one channel 1.88 wide, so **the
convergence has to happen somewhere**. Put it in the start deck, which has 0.63
layout units of drop over 7.34, and at 8 to 11 wu/s it *orders* the field by
lateral distance. Put it on the launch, at 25 to 43 degrees, and it *ejects*
the field. A mixing region only decorrelates if marbles keep enough speed to be
scattered rather than queued, and the only stretch with that much energy is the
one whose convergence throws them out.

Twenty geometries across two sessions, including both architectures this brief
asked for. The only one that ever reduced the span held a fifth of the field
up.

---

## 3. Routes - one ships, and the trade is measured

`routes="blue"`. The fork's geometry, its entry test and the measurement below
all stay in the tree.

| leg3's east guard | finish | escape | blue / orange |
|---|---|---|---|
| **shut (shipped)** | **0.979** | 0.021 | 94 / 0 |
| open 4 samples | 0.396 | 0.604 | 93 / 1 |
| open 7 samples | 0.323 | 0.625 | 61 / 33 |
| open 9 samples | 0.323 | 0.625 | 43 / 51 |
| open 12 samples (V1.1) | 0.312 | 0.635 | 40 / 54 |

Route *usage* is not the problem: at 9 samples the split is 43/57, inside
section F's band. Reliability is, and it is not a tuning question - every open
window loses two thirds of the field.

It is not the ridge (removing it entirely moves finish by 0.011), and not
orange's own guard (holding it open longer makes things worse, 0.312 down to
0.083 - it is containing, not obstructing). With leg3's guard never opened and
everything else built, finish is **0.979**: orange's lead and lobe colliders
are harmless.

The ejector is the opening itself. leg3's tail is banked 26 degrees - 1.7 more
than a marble at 43 wu/s needs to hold its radius - so the field is pressed
against the east wall, and the branch is on the outside of that turn. The wall
that must open is the one the field leans on, and a marble crossing it does not
land on orange: orange's floor is 0.66 to 0.77 **below** leg3's east lip
through the window.

The next step is named in the findings note: drive orange's lead height off
`leg3.surface_point(s, +CHANNEL_HALF)` - leg3's east *lip* - rather than off
its centreline.

---

## 4. Entertainment - survived

| | V1.1 | **V1.2** |
|---|---|---|
| lead changes a race | 4.55 | **4.09** |
| overtakes a race | 41.0 | 38.7 |
| winner lock fraction | 0.165 | **0.141** |
| winner's worst rank | 2.02 | 1.77 |
| median final margin | 0.467 s | **0.433 s** |
| collisions a race | 96.7 | 92.8 |

Four lead changes a race, the winner not settled until the last 14% and having
been as far back as second on average, and a median finish under half a second
apart. Section I's requirement was that fairness work not make the race
deterministic; fairness did not move, and the race did not either.

---

## 5. The selected seed

**Seed 569**, from 494 all-eight-finisher races.

    1  marble 5  slot 0   15.717 s
    2  marble 4  slot 2   15.800 s
    3  marble 3  slot 1   16.950 s
    4  marble 6  slot 5   17.433 s
    5  marble 0  slot 7   17.850 s
    6  marble 7  slot 4   18.567 s
    7  marble 1  slot 6   18.950 s
    8  marble 2  slot 3   19.367 s

**Thirteen lead changes**, a 0.083 s margin, and the winner starts in **slot
0** - the bay that wins 1.33% of the time - with slot 2, the bay that wins
24.5%, second. It was picked on race quality rather than on that, and it is a
fair illustration of what an 18.4 ratio is: a distribution, not a script.

Nothing about the physics was altered to obtain it. The V1.1 seed 83 is not
carried over.

---

## 6. Determinism

Seed 569, 20 repeats in one process and 20 more in fresh child processes.
Identical state digest, event digest, finish order, route assignment and finish
times across all forty.
`docs/validation/sloped_race_v1/determinism_v12.json`.

The replay's own contact check: 1921 frames, worst penetration well inside the
0.25 budget, and four brief `leg2[108]` findings where a spinner blade throws a
marble up to 0.23 simulation units clear of the floor. A marble hit by a paddle
leaving the floor is the obstacle working, not a containment failure.

---

## 7. The video

`output/sloped_race_v1/real_race_v12.mp4` - 1080x1920, 60 fps, no audio,
rendered from the authoritative replay only.

Camera coverage is thinner than the field deserves in three cuts - `long` at 3
of 8, `branch` at 2 and `merge` at 3 - because the field has spread by then and
there is one route to follow. Section K's ask is met where it can be: no cut is
empty, `establish`, `descent` and `obstacle` hold all eight, and the finish
holds five.

---

## 8. Remaining issues

1. **The start bias is 18.4 and is not a tuning problem.** The convergence from
   eight bays to one channel orders the field wherever it is put, because the
   start deck has 0.63 units of drop and the launch that has the energy also
   has the ejection. Fixing it needs drop, which means moving the start node -
   a macro-layout change.
2. **Orange ships disabled.** The opening that lets a marble cross leg3's east
   guard is the wall the 26-degree bank presses the field against, and orange's
   floor sits 0.66 to 0.77 below leg3's east lip through the window. The next
   attempt should drive the lead's height off the lip rather than the
   centreline.
3. **Finish is 97.7% against a 98% target**, with `leg2[80..99]` (52 losses of
   4800) and `leg1[80..99]` (32) the only concentrated sites left. Both are the
   obstacle corridor and the hairpin feeding it.
