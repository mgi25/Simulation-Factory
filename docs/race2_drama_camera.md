# Race #2: event density, continuity and a camera language

Branch `v28-race-drama-camera-lab`, from `origin/main` at `eaca65e`.
**This is a lab. Nothing here is merged and nothing in Race #1 is changed.**

---

## 1. Problem statement

Race Test #2's analytics say three things and they do not all point the same
way. The immediate PICK A COLOR opening worked. Stayed-to-Watch improved
strongly, so viewers now give the race a chance. And average viewing duration
says the middle does not hold them.

That is not a prettiness problem and it is not a duration problem. It is a
**dead-time** problem, and Race #1's geometry is where it comes from. The
sloped course is 237 layout units of centreline with five mechanisms on it - a
mechanism every 47 units, which at nine to fifteen layout units a second is a
new question every three to five seconds, with rolling in between. The camera
makes it worse rather than better: every cut is a fixed bearing about a station,
so a shot shows where the race *is* and never what it is about to hit.

## 2. The hypothesis this lab tests

> The middle fails because the course has long stretches in which nothing that
> could change the finishing order happens, and because the camera never shows
> the viewer what is coming.
>
> Both are fixable in geometry and in shot design. Neither is fixable by
> cutting the film shorter.

So the lab optimises one number:

**the longest span in which nothing competitively meaningful changes.**

Not duration, not density, not mechanism count. Density can be bought by piling
three events into one second and leaving six empty either side, which is
exactly the film the analytics complained about. The longest gap cannot be
bought that way.

## 3. Why continuity matters

The temptation is to cut the dead time out. The brief rules that out and is
right to: a marble race's satisfaction is that you watched it happen. A cut
that makes a viewer ask "how did that marble get there" spends the credibility
that makes the finish mean anything.

So the rule here is **fix the course, not the edit**. The final Short contains
no temporal omissions at all - see section 15.

---

## 4. Three concepts

All three were built as real, raceable courses on **one skeleton**: the same
switchback plan, the same 36.6 layout units of fall, the same drop start, the
same run-out. Only the width programme and what stands in the channel differ,
so the comparison is about competitive topology and nothing else. A comparison
in which one concept is also bigger measures the wrong thing.

| | topology | where order changes come from |
|---|---|---|
| **A Cascade Gauntlet** | single route, wide banked pan alternating with narrow corridor | the queue: a pan lets the field arrive abreast, a neck decides who leaves first |
| **B Braid** | two splits with a blade between the branches, each merging into the pan below | route choice, and the confrontation at the merge |
| **C Mechanism Line** | single route, four powered wheels and one gate | phase: a marble's wait at a wheel is its arrival time modulo the blade period |

24 seeds each, 192 racers each
(`docs/validation/race2/concepts.json`):

| concept | finish | all-8 | stuck | slot r | lead | ev/s | mean gap | worst gap | race | podium |
|---|---|---|---|---|---|---|---|---|---|---|
| cascade | 99.5% | 96% | 0.0% | −0.101 | 18.6 | 5.68 | 2.04 | **3.23** | 15.4 s | 0.661 |
| braid | 46.9% | 0% | 53.1% | −0.044 | 16.6 | 4.90 | 2.83 | **4.90** | 14.2 s | 1.151 |
| mechanism | **100.0%** | **100%** | 0.0% | **+0.018** | **20.0** | **5.95** | **1.59** | **2.00** | 19.2 s | **0.624** |

(These are the pre-hysteresis lead-change and density figures — see section 9
for why the numbers in the production benchmark are lower and better.)

### 5. Selected: C, the mechanism line

It wins on every column that matters, and one of them decides it: **the worst
longest-dead-interval over 24 seeds is 2.00 seconds.** The brief asks for a new
question every two to three seconds; that is the measurement of it, and neither
of the others gets under three.

**Braid is falsified, and usefully.** Its splits jam: the two branches cannot
both be as wide as the pan feeding them and still leave the blade somewhere to
stand, and the failure is not marginal - 53% of racers stuck. Worse, in the
races that did complete, the *more popular* branch of the first split cost its
takers 1.4 places of mean rank. A split that punishes the majority is not a
choice, it is a tax. Race #1 spent five sessions making one fork work; this is
a second, independent piece of evidence that **a fork is the most expensive
drama per unit of geometry available**, and Race #2 buys its drama elsewhere.

**Cascade is the honourable second.** Its shape is right and its lead-change
rate close, but it loses a racer in one race in twenty-five, and its worst dead
interval is 3.2 seconds — a stretch of banked hairpin where the field is simply
travelling.

The production course is called **SWITCHYARD**.

---

## 6. Module purposes

The module design rule's second question is the one that decides whether a
module earns its place: not what it physically does, but what it does to the
race *order*.

| module | what it does | what it does to the order |
|---|---|---|
| shelf + trapdoor | one panel hinged across the course drops away under all eight bays | **nothing, by design.** The only module whose job is not to sort |
| stud field | nine studs across the 5.9-unit head band | destroys the bay order while the field is still a clump and before anything narrows. This is the fairness mechanism |
| pan 1–5 | a banked hairpin, 4.6 units of clear channel | **recompresses** (a leader entering fast rides high, travels further, comes out level) and offers a **high line against a low line**, which is a route choice with no fork in it |
| drum | four wheels at 6.2 rad/s in a 2.8-unit corridor, 30 units in | the biggest single reordering, deliberately the earliest: the rest of the race is spent recovering from it rather than setting it up |
| sweep | one wheel at 2.2 rad/s sweeping the whole clear width | **shuts** the corridor for about a third of every turn. The only gate on the course, and a leader can be the one it catches |
| pair | four blades at 4.8 rad/s | **punishes the leader by phase** — the one mechanism whose output order is not monotone in its input order |
| last | the same at 3.4 rad/s | **separates** the field again, so the final pan has something to compress and the sprint has a gap to close |
| sprint | 2.2 units wide, falling, nothing on it | the last order change is visible because nothing else is happening |
| run-out | the deck past the line | not a race module: the winner can be photographed crossing, and the course is proved able to stop a field |

### The course, as geometry

176.5 layout units of centreline, 36.6 of fall, five switchbacks, in a plan of
**26.6 × 48.0**. Race #1 is 237 units in **43 × 83**. So Race #2 is 73% of the
distance in **38% of the plan area** — which is the whole argument about dead
travel, stated as geometry. Nothing on this course is more than about fifteen
units from the thing before it.

---

## 7. Fairness

Race #1's start cost five sessions and landed on one finding:

> A release that reads no marble's position cannot sort the field by position —
> and the release was never where the start went wrong. The **first
> constriction** was.

Race #2 takes both halves. The release is a single panel hinged on the
across-course axis, so every bay is the same distance from the hinge and loses
support in the same tick; `panel_release_times()` returns the eight times so a
test asserts they are one number rather than reading the prose. And **there is
no constriction after it** — the field falls 1.4 units onto a band as wide as
the bay row, and that band stays that wide until the stud field has scrambled
it.

Measured over **200 seeds / 1600 racers**:

| | |
|---|---|
| finish rate | see section 19 |
| **start-slot vs finish-rank correlation** | see section 19 |
| winner distribution | `docs/validation/race2/benchmark_switchyard.json` |
| route advantage | n/a — the switchyard has no branch. Its route choice is the line through a pan, measured as `line_choice` |

---

## 8. What counts as an event

The brief warns against inventing metrics to produce numbers, so an event is
defined once and narrowly:

> **An event is a moment at which the answer to "who is winning?" measurably
> changed, or was measurably put at risk.**

| kind | |
|---|---|
| `leader_change` | rank one changes hands |
| `top3_change` | the *set* of the leading three changes |
| `overtake_cluster` | swaps inside the leading four, merged within 0.30 s |
| `compression` / `separation` | the leading five cross a spread threshold, with hysteresis |
| `mechanism_hit` | a top-three racer meets a powered part (clustered per module within 0.5 s) |
| `line_choice` | the leaders straddle a pan's centreline — the high line against the low line |
| `route_split` / `route_merge` | a branch is committed to and resolved (unused by the switchyard) |
| `finish` | each crossing |

Deliberately **not** events: a marble touching a wall, a bank being ridden, a
wheel turning with nobody near it, a swap between seventh and eighth. Each is
motion, and mistaking motion for drama is the whole of what "the middle needs to
earn attention better" means.

### The hysteresis that made the numbers honest

The first measurement reported 32 lead changes in a 20-second race. Fourteen of
them were two marbles trading places every two frames inside the first second,
because eight marbles crossing a pan are level to within a millimetre and an
ordering that compares raw progress at 60 Hz swaps them on every sample. A
viewer sees one bunched pack there.

So the rank order is **sticky**: the previous ordering is kept unless a marble
leads its neighbour by `LEAD_MARGIN` — 0.8 layout units, or 1.4 marble
diameters. The reported lead-change count fell from 32 to 9 on the same race,
and it now means what a viewer would count.

---

## 9. Event-density metrics

Per race: count, events per second, and the gap list. The headline is
`longest_gap`; `dead_zones` lists every span over 1.6 s.

## 10. Hero seed

Chosen *after* the course was healthy across 200 seeds, never designed for. The
brief's list of what a hero race should contain is a weighted score
(`tools/race2_benchmark.py`), with one rule that is not a weight: **a hero race
must have all eight finishers.** A film in which a colour the viewer picked
vanishes has broken its own promise.

Selected: see section 19.

---

## 11. Camera language

> **SHOW THE RACERS, SHOW THE NEXT THREAT, SHOW THE CONSEQUENCE.**

Seven modes, each with one job:

| mode | for |
|---|---|
| `hook_close` | eight racers filling the frame at rest, then the floor going |
| `pack_track` | the leading group in the near two thirds, the course direction in the far third |
| `obstacle_anticipation` | the mechanism in the foreground, the field arriving into it |
| `action` | close and low inside a compression, where the contact is |
| `route_choice` | both branches at once (built, unused by the switchyard) |
| `final_sprint` | low and alongside, so the closing gap is the whole picture |
| `winner_payoff` | the winner across the line and far enough past it to be read |

Three things are different from Race #1's camera:

**The frame is solved from the pack, not from the course.** Every mode sizes
its distance so the leading group spans a stated fraction of frame *width*. A
camera placed at a fixed reach from a station frames whatever the station is,
and when the field is strung out the racers in it are four pixels each.

**The aim leads the pack.** `aim = (1 − look_ahead)·centroid +
look_ahead·next_event`, with `look_ahead` around 0.3.

**Anticipation is its own mode.** A look-ahead blend can only lead the aim; it
still leaves the camera behind the pack with the mechanism edge-on.
`obstacle_anticipation` puts the lens *past* the mechanism looking back up the
course.

### The schedule is station-driven

The first build anchored shots to phases and produced seven cuts over nineteen
seconds, five of them the same mode, and **no anticipation shot at all** —
because a phase opens when the field enters its first stage, which is a pan, and
by the time the wheel in the corridor below is hit there is not enough window
left to cut three shots from. A station is the right anchor because a station is
the thing the viewer is being asked a question about.

---

## 12. What the camera cost in geometry

Three corrections, all found by rendering and all worth recording.

**The bearing convention was inverted.** The lens stands at
`aim + bearing · reach`, so a bearing equal to the heading puts it *downhill*
looking back — a head-on shot, not a chase. Every tracking shot was authored as
if zero meant "behind". The first hook render was the outside of the start's
back wall, full frame.

**A folded course occludes itself.** Race #1's legs are forty units apart;
the switchyard's are five to nine. Four of seven shots on the first render had
the lens under the channel. The authored elevation is now a *floor*: the solver
raises it in four-degree steps until the leading group is visible past the rest
of the course, stopping at 44° because past that it is the map view the brief
rules out.

**A clear sightline is not a clear shot.** The sprint cut had all three leading
racers visible and was unusable: the lens sat twelve units out among the
switchback legs with the underside of the pan above filling the top half of
frame. The sightline test cannot see that — the problem was beside the lens, not
in front of it. Hence `LENS_CLEARANCE` (2.4 units of clear air round the lens)
and `MIN_REACH` / `MAX_REACH`.

### The trench, and why the wall came down

The hardest of them. `sloped.track.channel_profile(scale)` multiplies the whole
cross-section by the run's scale — including the guard rail. Race #2 runs at
scale 2.0 so eight racers can spread across a pan, and the marble is still
0.285, so the wall became **1.60 layout units** of rail around a 0.57 marble.

Seeing a marble over its own near rail needs `atan(containment / half width)` of
depression. At 1.60 in a 1.33 half-width corridor that is **50 degrees** — the
map view. Seed 140's `last_impact` was the measurement: four racers dead centre
of frame by projection, **none visible in the render**, every sightline crossing
`corr4`'s own guard at 94% of the way to the marble.

Capping the wall costs containment, and `tools/race2_wall.py` measured the bill
over 40 seeds each:

| cap | finish | all-8 | escape | look-down |
|---|---|---|---|---|
| 0.62 | 77.7% | 13% | 21.9% | 20° |
| 0.85 | 97.2% | 78% | 2.5% | 18° |
| 1.60 (uncapped) | 99.9% | 99% | 0.0% | 50° |

The tall wall was doing real work: a marble carrying 20 units a second into a
4.8-radius hairpin rides most of the way up the outside.

**But only the banked part of a run needs it.** So the cap is 0.70 everywhere
and the pans carry a **guard boost** over their turn — the mechanism
`sloped.track` already has and describes as "a containment repair belongs to a
stretch and not to a whole run". A pan gets 1.66 of rail through its bank and a
corridor 0.70; because a pan is also twice as wide, the look-down each demands
comes out the same — about 25° over a pan and 26° over a corridor. Both are the
three-quarter view the brief asks for.

---

## 13–18. Results

See section 19 for the measured tables: phone review, continuous-race review,
Short pacing, comparison with Race #1, remaining weaknesses and the recommended
next step.

---

## 19. Measured results

*(filled in from the final benchmark and render pass — see
`docs/validation/race2/`)*
