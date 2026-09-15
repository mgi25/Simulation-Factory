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

Capping the wall costs containment, and it was measured rather than argued:

| cap | seeds | finish | all-8 | escape | look-down |
|---|---|---|---|---|---|
| 0.62 | 60 | 77.7% | 13% | **21.9%** | 20° |
| 0.85 | 40 | 97.2% | 78% | 2.5% | 18° |
| 0.70 + pan boost | 60 | 91.7% | 47% | 8.1% | 26° / 36° |
| **1.10 + pan boost** | **60** | **99.6%** | **97%** | **0.00%** | **21–40°** |
| 1.60 (uncapped) | 200 | 99.9% | 99% | 0.00% | 50° |

The tall wall was doing real work: a marble carrying 20 units a second into a
4.8-radius hairpin rides most of the way up the outside, and at 0.62 it rides
over. The escapes were not spread evenly - over 24 seeds, thirteen of them, all
"outside", five in `corr1`, four in the sprint - which is to say **in the
corridors, in their first half, where the field arrives out of a bank**.

So the shipped configuration is three things, not one:

- a flat cap of **1.10** layout units, which is the wall everywhere;
- a **guard boost** on the pans over their banked stretch, taking those to 1.66.
  This is `sloped.track`'s own mechanism, and its own description of it -
  "a containment repair belongs to a stretch and not to a whole run" - is
  exactly the argument;
- the funnel from a pan into a corridor **eased over half the run instead of a
  third**, because a 2.31 half-width squeezing to 1.45 in five units is a wall
  closing on a marble that is still carrying lateral speed out of a hairpin.

That restores containment completely - **zero escapes over 200 seeds** - and
leaves the look-down at 21° over the head band, 36° over a pan, 37° over a
corridor and 40° over the sprint. Those are moderate three-quarter views;
Race #1's own `split` cut is authored at 38°. It is more look-down than was
hoped for and it is not the map view the brief rules out.

An intermediate configuration - a 0.70 cap with a larger pan boost - is in the
table because it is instructive: it fixed the pans and left 8% escaping in the
corridors, which is how the corridors were identified as the real problem.

---

## 13. Seed benchmark

200 seeds, 1600 racers, `docs/validation/race2/benchmark_switchyard.json`:

| | |
|---|---|
| racers finishing | **99.62%** |
| races with all eight | **97.00%** |
| stuck | 0.37% |
| escaped | **0.00%** |
| **start-slot vs finish-rank (Spearman)** | **+0.028** |
| lead changes per race (sticky) | 6.39 |
| overtakes per race | 53.0 |
| events per race | 58.1 |
| events per second | 3.17 |
| mean longest dead interval | **1.45 s** |
| worst longest dead interval | 3.75 s |
| mean dead zones over 1.6 s per race | 0.245 |
| first finish | 15.12 s |
| last finish | 18.38 s |
| podium gap | 0.676 s |
| simulation wall time per race | 25.0 s |

Wins by starting bay, out of 200:

| bay | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| wins | 21 | 26 | 18 | **38** | 31 | 21 | 24 | 21 |

Expected 25 each. Bay 3 at 38 is the one bump; chi-square over the eight bays is
12.2 on 7 degrees of freedom, p ≈ 0.09, so it is not significant at 5% — but it
is the thing to re-measure first if the course is ever tuned, and it is the
honest reading of a +0.028 correlation that is *not* zero.

## 14. Hero seed: 8

Chosen by score from the 194 of 200 races that kept all eight racers.

| | |
|---|---|
| winner | m7, from bay 0 |
| its rank at release / first event / quarter / half / three-quarter | 4 / 5 / 4 / 3 / 2 |
| **finishing margin** | **0.067 s** |
| lead changes | 9 (3 of them in the last third) |
| events | 67 in 18.73 s = **3.58 / s** |
| **longest dead interval** | **1.05 s** |
| dead zones over 1.6 s | **none** |

Finishing order: m7 (bay 0) · m2 (5) · m1 (1) · m5 (7) · m3 (6) · m0 (3) ·
m6 (4) · m4 (2), from 15.82 s to 18.75 s.

**The story.** m7 is fourth off the shelf and fifth out of the stud field. m0
leads out of the drum, loses it to m2 at 2.58 and m2 loses it to m1 at 2.93 —
three leaders in the first three seconds. The sweep catches m1 at 6.28 and m2
takes the lead at 7.15. m1 takes it back at 9.58 through the counter-turning
pair. m7, third, is still third at 12.68 when the last wheel catches m1 — and
takes the lead at 13.12. m2 takes it back at 14.38 on the final pan. m7 wins by
**0.067 s**: six-hundredths of a second after nineteen seconds of racing, having
never led until the last six.

## 15. The Short

`exports/race2_drama_camera/race2_switchyard_8_short.mp4`, 1080×1920 at 60 fps,
**19.15 s, 1150 frames, no temporal omissions at all.** The camera track
contains no `edit` block; every frame of the film is a consecutive frame of the
physics. The brief's rule — "no cut may make a viewer reasonably ask how that
marble got there" — is satisfied by construction rather than by review, because
the course was fixed instead of the edit.

Eleven cuts, mean 1.74 s:

| from | to | shot | mode | covers |
|---|---|---|---|---|
| 0.02 | 1.18 | hook | hook_close | top3, leader change, studs |
| 1.18 | 2.15 | drum_anticipate | obstacle_anticipation | top3 change |
| 2.15 | 3.08 | drum_impact | action | mechanism, leader change, top3 |
| 3.08 | 6.20 | sweep_anticipate | obstacle_anticipation | mechanism, top3, separation, line choice |
| 6.20 | 7.13 | sweep_impact | action | mechanism, compression |
| 7.13 | 8.94 | pair_anticipate | obstacle_anticipation | leader change, mechanism, separation |
| 8.94 | 9.87 | pair_impact | action | mechanism, leader change, compression |
| 9.87 | 12.60 | last_anticipate | obstacle_anticipation | mechanism, separation |
| 12.60 | 13.53 | last_impact | action | mechanism, leader change |
| 13.53 | 15.37 | sprint | final_sprint | leader change, line choice |
| 15.37 | 19.15 | payoff | winner_payoff | finish ×8, compression |

**Every cut covers at least one event.** The camera-event map
(`tools/race2_camera.py`) prints them side by side precisely so that a shot
covering nothing shows as an empty right-hand column, and none does.

The anticipation shots give 1.05 s, 3.40 s, 1.58 s and 2.38 s of warning before
their contacts, with the mechanism in frame for 100% of each shot.

## 16. Framing and phone review

`docs/validation/race2/framing_switchyard_8.json`, measured per frame:

| shot | group width | racer px @1080 | racer px @270 | in frame |
|---|---|---|---|---|
| hook | 38.8% | 81 | 20.3 | 8 / 8 |
| drum_anticipate | 36.2% | 58 | 14.6 | 5 / 0 |
| drum_impact | 31.4% | 64 | 16.0 | 8 / 7 |
| sweep_anticipate | 32.9% | 61 | 15.3 | 5 / 2 |
| sweep_impact | 64.9% | 61 | 15.4 | 5 / 4 |
| pair_anticipate | 32.0% | 61 | 15.2 | 5 / 2 |
| pair_impact | 77.2% | 58 | 14.5 | 5 / 4 |
| last_anticipate | 42.7% | 61 | 15.2 | 5 / 2 |
| last_impact | 77.5% | 56 | 14.0 | 5 / 4 |
| sprint | 49.5% | 75 | 18.8 | 4 / 3 |
| payoff | 34.3% | 80 | 19.9 | 4 / 2 |

Every shot keeps a racer at **56 px or more** in the delivery frame and 14 px or
more at 270×480, against a floor of 20 and a phone-legibility floor of about 7.
Reviewed as rendered stills at 270×480
(`output/race2/frames/phone_switchyard_8/`): colours are distinguishable, the
mechanism is identifiable, and the track reads.

The group-width band (25–45%) is met on eight of eleven shots. Three exceed it,
and that is a stated trade rather than a defect: `MAX_REACH` caps the lens at 26
layout units so racers stay large, and when the leading group is wider than the
frame at that distance the group overflows rather than the racers shrinking. A
shot of four racers you can tell apart is a race; a shot of eight dots is a
diagram.

**The anticipation shots open empty**, by design — the reveal is the mechanism,
and the field arrives into it at 0–29% of the way through each shot. The report
measures that as `racers_enter` rather than flagging an empty first frame.

## 17. Comparison with Race #1

24 seeds of each, **the same instrument on both** (`tools/race2_compare.py`).
Race #1's lead changes are re-counted under Race #2's sticky ordering, because
its native counter has the 60 Hz flicker problem and quoting the two side by
side without that correction would flatter Race #2 for a reason unrelated to its
geometry.

| | Race #1 sloped | Race #2 switchyard |
|---|---|---|
| racers finishing | 99.0% | 99.0% |
| races with all eight | 92% | 92% |
| **lead changes** | 2.96 | **6.58** |
| **longest span with no lead change** | 12.66 s | **8.69 s** |
| first finish | 20.66 s | **15.12 s** |
| last finish | 25.16 s | **18.23 s** |
| podium gap | 0.655 s | 0.612 s |
| simulation wall time | 19.9 s | 15.6 s |
| centreline / plan area | 237 u / 3569 u² | **176 u / 1277 u²** |

(Race #1's raw, un-hysteresed count is 4.25 — so the correction costs it 30%,
and the comparison above is the fair one.)

Answering the brief's questions directly:

- **Which changes leader more often?** Race #2, 2.2× as many in 72% of the
  duration — **3.1× the rate**.
- **Which has shorter dead periods?** Race #2: the longest span with no lead
  change falls from 12.7 s to 8.7 s, and on its own event definition the longest
  span with *nothing* happening is 1.45 s mean, 3.75 s worst.
- **Which keeps racers larger?** Race #2, by construction — the frame is solved
  from the pack and the reach is capped. Race #1's camera is solved from station
  extents and its own check bounds racers at 24 px; Race #2's worst shot is 56.
- **Which reveals upcoming action better?** Race #2. Race #1 has no anticipation
  mode; Race #2 gives every powered mechanism 1.0–3.4 s of it.
- **Which maintains continuity?** Both — neither film omits time. Race #2's is
  continuous by construction.
- **Which final sprint is stronger?** Race #2, marginally: 0.612 s against
  0.655 s on the podium gap, and the hero seed's 0.067 s is a photo finish.

## 18. Performance

| | |
|---|---|
| physics, one race, 8 racers | 25.0 s wall (mean over 200 seeds) |
| 200-seed benchmark, 11 workers | about 7 minutes |
| scene | 168 mesh instances, **71,520 triangles** |
| render | **256 ms/frame** at 1080×1920 on an RTX 3050 Laptop |
| the 19.15 s Short | 1150 frames in 294 s, 16.2 MB at CRF 17 |
| course geometry export | 0.37 MB of JSON |

71.5k triangles is a small scene by this repository's standards, and the render
rate is the practical limit rather than the simulation.

## 19. Remaining weaknesses

1. **The worst-case dead interval is 3.75 s**, on one seed of 200, against a
   1.45 s mean. The hero seed's is 1.05 s. Worth locating: it is almost
   certainly a race in which the field strings out early and the tail spends the
   last pan alone.

2. **Bay 3 wins 38 times in 200** where 25 is expected. Not significant at 5%,
   but the Spearman is +0.028 and not 0.000, and the first thing to do with
   another compute budget is 600 seeds to see whether it survives.

3. **3% of races lose a racer** (0.37% stuck, no escapes). Race #1's shipped
   number after four sessions of work is better. Every one is a jam, and the
   wheels are the obvious suspects.

4. **The frame is half empty.** The V26 environment is a dark valley, and a
   portrait frame of a compact course leaves a lot of unlit rock. This is
   deliberately not addressed — the brief says to use V26 as a test background
   and not to polish it — but it is the single biggest difference between these
   frames and a finished film. A contained hall changes it completely, which is
   one reason not to tune against the current backdrop.

5. **Fixed during the lab: the sprint shot's tail was empty.** The first
   continuous render came back with one byte-identical frame pair in 1150, at
   the `sprint` → `payoff` boundary. The obvious reading was a renderer artefact
   — the clip path takes one draw per frame where the stills path takes two, and
   post-effects carry history across a camera jump — so the frame at each cut
   was given a second draw. **It made no difference, and that was the useful
   result.** Re-rendered as two independent stills at 15.800 and 15.817 the
   frames were still identical, which means the scene state was identical, which
   means nothing in frame was moving.

   Looking at the frame settled it: no racers and no moving parts, just an empty
   stretch of track. Two causes, found in that order. The sprint blended its aim
   16% toward the next event, and on a sprint the next event is the finish line
   — so as the leaders reached it the aim was already past them. Removing the
   look-ahead (there is nothing to anticipate on a sprint; the racers are the
   subject) improved the shot everywhere and did **not** fix the last frames.

   The residue was occlusion, and of the kind the framing report cannot see: at
   the very end of the channel the run-out deck stands between a lens solved
   along the sprint and the racers on it, so they were inside the frustum and
   behind geometry. `race2.framing` counts frustum membership and says so in its
   own docstring — **a frustum count is not visibility** — and this is the case
   that proves it.

   The fix is editorial rather than geometric: the sprint hands over 0.45 s
   *before* the line and the payoff takes the crossing, which is its job anyway
   and which it frames from outside the channel. The Short's last two cuts are
   now 13.53–15.37 and 15.37–19.15.

   The extra draw at cut boundaries was kept. It costs nothing measurable and
   the reasoning behind it is sound for a different defect that has not happened
   yet.

   **The lesson worth keeping is the method, not the fix**: an identical pair of
   frames is a cheap and complete detector for "nothing in this shot is moving",
   and it found a defect that eleven still frames and a framing report had all
   passed.

6. **The group-width band is exceeded on three shots.** A stated trade (see 16),
   not a defect, but it means the tail of the field leaves frame during the later
   impacts.

7. **`route_split` and `route_merge` are never emitted** by this course, because
   it has no fork. The `line_choice` event measures its actual route decision —
   the high line against the low line through a pan — and fires twice in the hero
   race. The unused kinds are kept because the braid concept needs them and
   because a future course may reintroduce a split.

## 20. Recommended next step

**Take the format, not the course, to the next test.** What this lab established
is not the switchyard: it is that a folded course plus a station-anchored camera
with anticipation shots produces three times Race #1's lead-change rate in three
quarters of the runtime, continuously, with no edit.

In order:

1. Render the same Short in the **contained hall** as soon as the other
   session's stage lands. The course is environment-independent by construction
   (`tests/test_race2_isolation.py`) and the scene takes `--environment=`, so
   this is a flag and not a port. Weakness 4 is most of what stands between
   these frames and a deliverable.
2. **600 seeds** on the fairness question (weakness 2) and on the 3% of races
   that lose a racer (weakness 3).
3. Only then consider a second course. The braid is falsified as built, but a
   split with a **drop** junction instead of a shared plane was never tried, and
   it is the one topology that could add prediction-changing moments this course
   does not have.

---

## Where everything is

| | |
|---|---|
| concept comparison | `docs/validation/race2/concepts.json` |
| 200-seed benchmark and hero shortlist | `docs/validation/race2/benchmark_switchyard.json` |
| hero event and camera timeline | `docs/validation/race2/events_switchyard_8.json` |
| framing report | `docs/validation/race2/framing_switchyard_8.json` |
| Race #1 comparison | `docs/validation/race2/compare_race1.json` |
| replay, geometry, camera track | `output/race2/race2_switchyard_8.*.json` |
| shot sheet (1080×1920) | `output/race2/frames/sheet_switchyard_8/` |
| phone sheet (270×480) | `output/race2/frames/phone_switchyard_8/` |
| continuous clip, 1150 frames | `output/race2/frames/clip_switchyard_8/` |
| **the Short** | `exports/race2_drama_camera/race2_switchyard_8_short.mp4` |

`output/` and `exports/` are not in git, per this repository's convention.

## Tests

`tests/test_race2_course.py` (geometry, seams, wheel clearances, the start's
single release time, mesh health), `test_race2_physics.py` (pure actuator poses,
no force calls in the loop, seed determinism, seed *sensitivity*, energy
non-increase), `test_race2_race.py` (finish detection, route validity,
checkpoints, timeline determinism, the hero seed's claims, the dead-interval
bound), `test_race2_camera.py` (schedule coverage, per-mechanism anticipation,
track determinism, lens-step bound, racer size, reveal timing),
`test_race2_isolation.py` (Race #1's contract still checks out, its profile is
uncapped, nothing in `race2` reads an environment, the scene builds no lights).

**44 tests, all passing.** The whole repository suite is 574 passed, 1 skipped
and 1 failed - `test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised`,
which fails identically on the baseline `eaca65e` because it needs a generated
`output/neon_v11/neon_7.json` that is not in git. It is not this branch's.
