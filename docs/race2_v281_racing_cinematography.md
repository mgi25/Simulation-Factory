# Race #2, V28.1: racing cinematography

Branch `v281-racing-cinematography`, from `origin/v28-race-drama-camera-lab` at
`8a0f541`.
**This is a camera lab. The race is not touched, the environment is not touched,
and nothing is merged.**

---

## 1. Why the V28 camera failed

V28 solved the *race* problem and the analytics say so: SWITCHYARD on seed 8 is
19.15 s, 67 events, 3.58 a second, nine lead changes, a 1.05 s longest dead
interval and a 0.067 s winning margin. None of that is in question here and none
of it is changed.

What failed is the filming. The V28 Short is **eleven cuts in 19.15 seconds,
mean shot 1.74 s**, and every one of those cuts covers a real event. That is
precisely the problem: the film is a correct *index* of the race rather than a
view of it. The viewer's loop is

> find the racers → watch the event → cut → find the racers again → cut → find
> the racers again

and the cost of that loop is measurable. Re-measured with this branch's
instrument, on its own rendered track:

| | V28 |
|---|---|
| hard cuts | 10 |
| mean shot | 1.74 s |
| share of the film inside its two longest takes | **36%** |
| screen-direction reversals across cuts | **5** |
| worst pack jump at a cut, in half-frames | **1.784** |
| worst lens-angle change across a cut | **123.7 deg** |
| minimum lens clearance | **-6.60 units** |
| racers, delivery frame | 57.5-85.2 px |

The last two are the ones that matter. **1.784 half-frames is the pack landing
most of a frame-width away from where it just was** - the eye has to hunt for
the race on almost every cut. And five screen-direction reversals is the film
telling the viewer the race turned round when it did not: V28 anchors each shot
to a fixed bearing about a *station*, and the switchyard reverses direction five
times, so consecutive stations are filmed from opposite sides of the racing
axis.

A negative clearance is the third row worth stopping on: **V28's lens spends
part of the film 6.6 layout units inside the course's own envelope.** That is
not a rendering fault - the shots it produces are the ones the doc describes -
but it is the measurement of a camera placed by bearing and reach from a station
rather than by a solve against the geometry, and it is why V28 needed a per-frame
lift loop at all.

A second, quieter failure shows up in the same instrument. V28's anticipation
shots stand past a mechanism looking back up the course, and measured
frame-by-frame they spend **46.7 to 58.5% of their samples with the active pack
outside the frame width**. Its `hook` has 31.4% of its samples with the racers
behind geometry, and its `sprint` has 56.2%. The shots are correct compositions
of mechanisms. They are not shots of a race.

| V28 shot | active pack outside the frame | behind geometry |
|---|---|---|
| `hook` | 0.0% | 31.4% |
| `drum_anticipate` | 50.0% | 37.9% |
| `sweep_anticipate` | **58.5%** | 10.9% |
| `pair_anticipate` | 53.4% | 13.8% |
| `last_anticipate` | 46.7% | 16.5% |
| `sprint` | 0.0% | **56.2%** |
| `payoff` | 31.7% | 0.0% |

The four `*_impact` shots are the good ones - 0 to 15% out of frame and nothing
occluded - and they are 0.9 to 1.6 s each. **V28 films the collisions well and
spends the rest of the film elsewhere.**

---

## 2. Racing cinematography: the four rules this branch works to

**FOLLOW FIRST, ANTICIPATE SECOND, CUT ONLY WHEN NECESSARY.** Stated as three
things the code does:

1. **The camera travels along the course with the pack**, rather than being
   placed near it. That is `race2.spine` and `race2.rig`, and it is what makes a
   six-second take possible.
2. **Position follows the racers; orientation reveals what is next.** The aim is
   blended toward the course ahead - but the blend is a *ceiling* which is pulled
   back whenever it would cost the racers their place in frame (section 5).
3. **A cut lands on a physical moment or not at all.** Every cut in every
   candidate is on the frame a wheel first touches the leading group; there is no
   cut for variety, and `race2.flow` prints the reason beside each one.
4. **The last mechanism to the line is one take.** Not a preference: a rule.

---

## 3. The active pack

The viewer picked a colour and we do not know which. That rules out following
the leader. The definition, in full:

> **The active pack is the leader, plus every racer within `PACK_GAP` of the
> leader in course arc length, floored at `PACK_MIN` and capped at `PACK_MAX`.**
>
> `PACK_GAP` = 4.5 layout units (about eight marble diameters), `PACK_MIN` = 3,
> `PACK_MAX` = 4.

Three things about it are load-bearing:

**Gaps are measured along the spine, not in world space.** On a course that
folds back on itself five times, a racer eight world units from the leader can
be a whole leg behind. Arc length is how a race measures a gap.

**The floor is what answers the escape case.** The brief asks what the camera
should do when the leader breaks clear while five fight behind, and does not
settle it. The floor does: the gap test alone would return one racer and the
camera would frame an empty leader, so the floor of three keeps the anchor
*between* the leader and the chasers and widens the frame to hold both. It
neither abandons the leader nor pretends the fight is not the story. On the hero
seed the floor binds on **460 of 2401 frames (19%)** - so this is a real case,
not a hypothetical one.

**The cap is what stops one tail racer destroying the framing.** It binds on
1761 frames (73%), which is the switchyard working as designed: the field is
genuinely bunched, and framing all eight at a readable size is not available.

A 6.0/5 pack was tried first and is worse: the wider group is more strung out,
the rig has to trail further to keep its back marker in front of the lens, and
the racers came out at 80 px against 85. Nothing else moved.

---

## 4. The chase-rig architecture

Four pieces, deliberately separable so a second course can reuse them.

### 4.1 `race2.spine` - the course as one arc-length curve

The eleven runs concatenated into one polyline with a cumulative arc length,
each sample carrying its point, horizontal tangent, horizontal right, banked up,
half width and guard height. A camera is then placed at an *arc length*, and
"where is the pack" is a scalar.

**This is what solves the switchback problem.** A camera that trails the pack
*along the spine* inherits the course's own reversal: when the course turns back
the camera turns with it, the racers still recede from the lens, and the screen
direction is preserved. A camera that stands off to one side in *world* space
does not - the pack crosses frame left-to-right on one corridor and
right-to-left on the next, and nothing repairs that afterwards. The measurement
is in section 10: **five reversals for V28, zero for all three candidates.**

The spine also carries an **8-unit straight tail past the finish**. The course
ends at the line; the race does not. The switchyard's field rolls five to seven
units onto the run-out and spreads across it, and a camera whose arc pins at the
last sample has to solve its framing by standing further and further out - which
took the finish lens twenty units downcourse, looking back over the deck's own
edge, with a fifth of the leading group behind it.

### 4.2 `camera_rail` - where a lens can actually stand

A folded course occludes itself. That is V28's finding and this branch does not
repeal it; what it does is stop rediscovering it sixty times a second. The rail
solves, **once per course**, a world azimuth and a height per sample, by a
forward walk with a continuity penalty. Occlusion is therefore solved offline,
against the course rather than against a race, and the answer is continuous by
construction - V28's per-frame lift loop could not be, because it has no
previous frame.

The solved rail on the switchyard:

| | |
|---|---|
| azimuth | 91.8 to 101.8 degrees, against a derived downhill of **93.1** |
| height above the channel | 2.5 to 8.9 layout units |
| minimum clearance | **2.41** units, against a 2.4 target |
| sightlines clear | 93% |
| maximum turn | 0.51 degrees per layout unit |

**The direction is derived, not chosen.** `Spine` fits a plane to the course -
`y = a + bx + cz` - and the rail's preferred azimuth is the plan direction of
steepest descent. The switchyard loses 0.649 units of height per unit of +Z, so
downhill is +Z to within three degrees, and that is where the lens has to be:
the downhill side of any leg is *above* the next leg, and the uphill side is
*below* the previous one. A lens 9 units upcourse of `corr2` sits inside
`corr1`'s guard envelope; the same lens downcourse sits eleven units clear above
`corr3`. A course that folded the other way would get the other answer from the
same three lines, and `test_the_downhill_direction_is_derived_from_the_geometry`
checks exactly that by mirroring a synthetic plane and by tilting one toward -X.

**That test is also the honest limit of the reusability claim.** Every course in
`race2` - the switchyard and all three concepts - is built on *one centreline
skeleton*, which is deliberate (V28 compared its concepts on one skeleton so the
comparison was about topology) and which means solving a rail for `cascade` and
for `switchyard` returns the same numbers and proves nothing. The architecture
is course-independent by construction - `camera_rail` takes a `Spine` and a rig
is seven numbers - but **nothing here demonstrates it on a genuinely different
plan**, and that is the first thing to do with a second course.

### 4.3 `race2.rig` - seven primitives

`chase_rear_3q`, `chase_pack`, `chase_side`, `compression_follow`, `bend_orbit`,
`finish_chase`, `hook_release`. A rig is a name and a handful of numbers: how
far it trails **along the spine**, how far out it stands, how much it adds to
the rail's height, how far ahead it looks, its lens, and how much of the frame
the group should fill. Everything else - which way is out, how high is clear -
is the rail's, already solved.

Two are worth singling out:

- **`bend_orbit` is not a special case.** It is a chase with a 12.5-unit trail,
  so the lens is still entering a hairpin while the pack is leaving it, and the
  turn happens in front of the camera. No new mechanism; just lag.
- **`finish_chase` cranes up as the winner crosses.** The run-out is a
  twelve-unit dish and the field spreads across it, so a lens held at the
  sprint's height is looking *along* a deck at marbles standing on it. Four and
  a half units of rise, ramped over 3.2 units of arc past the line, keyed on the
  crossing rather than on a clock - the shot stays low through the sprint, where
  low is the drama, and rises as the subject stops being a contest and becomes a
  field arriving. **A rise is not a cut; the hard rule holds.**

### 4.4 The trail is adaptive

`trail = max(rig.trail, pack rear extent + 3.0)`. The authored number is what
the shot wants; this is what the field allows. A lens that trails the pack's
mean by less than the pack's own spread has the back of the field level with it
or behind it, and **a marble level with the lens projects to the frame edge
whatever the reach is** - which is where 43% of the opening's active pack was
going, with the framing solve reporting the group comfortably inside 80% of
frame width because the marbles it could still see were.

---

## 5. Smoothing, and the finding that mattered most

Every follower is a **critically damped spring**, integrated implicitly:
unconditionally stable, no overshoot, no ringing, closed form per frame, so two
runs on one replay agree to the byte. They run on the rig's own parameters - the
lens's arc along the course, its reach, its height, its lens, its aim - and the
world position is *constructed* from the smoothed values. Nothing smooths a
solved world position after the fact, because that lets the lens leave the rail,
which is the one place the course is known to be clear.

Half-lives are 0.18-0.34 s on position and aim, 0.32 s on height, 0.50 s on
reach, 1.4 s on the lens.

### The velocity feed-forward

**A critically damped spring tracking a moving target lags it by a constant, and
the constant is proportional to the target's speed.** For this integrator the
steady-state error against a ramp is `2 * rate / omega`, which is
`1.19 * half_life * rate`. Textbook, easy to forget, and on a racing camera it is
not a subtlety - it is the defect.

Measured on the first build: the opening shot ended with the pack's centroid at
**screen x of -1.34**, a third of a frame outside the left edge, while every
framing solve in the film reported the group comfortably inside its target.
Nothing was wrong with the solves. The pack was doing 15 layout units a second,
the aim spring had a 0.24 s half-life, and `1.19 * 0.24 * 15` is 4.3 layout
units - which at that shot's 20-unit depth is exactly the 1.3 half-frames that
were missing.

So the pack's own velocity is passed to the springs and they aim that far ahead.
The lag against a steady ramp cancels; the damping still does its work on
everything that is not steady.

**What it bought, on the same build with nothing else changed:**

| | before | after |
|---|---|---|
| worst pack jump at a cut | 1.635 | **0.285** |
| worst scale jump | 1.33 | **1.19** |
| final sprint, top 3 visible | 75% | **82.7%** |
| final sprint, winner visible | 81% | **96.7%** |
| finish visible before the crossing | 2.22 s | **2.92 s** |

This is the single largest improvement in the session and it is four lines of
code.

### The screen-space solves

Two more corrections, both of the same shape - a quantity was being computed in
world units when the thing that mattered was on screen.

**The reach is bisected on the projected span.** V28 sizes its reach from the
greatest distance between two of the leading group and treats it as horizontal,
calling that the conservative reading. It is, for a camera at a 60-degree
bearing. It is the wrong reading for a chase: a trailing lens looks *along* the
course, so a group strung over nine layout units of track is nine units **deep**
and perhaps two wide. Sizing the frame as if it were nine wide pinned the reach
to its own ceiling on every frame of every candidate, cost the racers a third of
their size, and *still* let the pack overflow - because the number being solved
had almost nothing to do with the number that was overflowing.

**The look-ahead blend is a ceiling, not a value.** "Twelve units ahead along
the course" can be ninety degrees off the direction of travel; round a hairpin it
is almost behind. A fixed 30% blend swings the lens off the pack entirely. So
`_hold_aim` takes the largest blend that keeps every framed racer within 0.70 of
frame centre, by bisection. The look-ahead is then self-limiting: strong where
the course runs straight ahead and it costs nothing, weak exactly where it would
cost the racers.

### The height is an angle, not a height

The rail solves a height at its own nominal reach; what that pair encodes is a
**depression angle**, and the flown reach is often 1.75 times the nominal because
the framing solve has pulled back. Holding the height while the reach grows
halves the angle the lens looks down at, and a lens 18 units out and 5 up is 15
degrees above a channel whose own guard needs 20 to see over. The first rendered
contact sheet of this branch was exactly that: the track edge-on as a thin white
ribbon. The height now travels with the reach, capped at 45 degrees so a shot
never becomes the plan view.

---

## 6. Screen direction and the switchback

The switchyard reverses local direction five times. The rule this branch works
to:

> **A reversal inside a shot is not a reversal.** The racers really do change
> direction; when that happens continuously in front of a moving lens the viewer
> watches the course turn and understands it. Only a reversal across a hard cut
> is one.

That distinction is only *available* because the rig trails along the spine. The
camera rotates with the course, so the pack recedes throughout and the hairpin
reads as a hairpin.

Measuring it took a correction of its own. The first version measured the pack
centroid's screen drift, which is the wrong thing on a camera that works: a
chase rig holds the pack in the middle of frame, so its centroid barely moves and
the sign of "barely" is noise. Measured that way the candidates reported two to
four reversals each, all at cuts where nothing reversed - and the reason the
count had been *zero* before the feed-forward was that the pack was drifting out
of frame, which gave the measurement something large and consistent to read. The
instrument now projects the racers' **world velocity** into the lens's right
vector, with a deadband under which a shot is a rear chase and has no screen
direction to reverse.

---

## 7. Camera A - continuous chase

Four shots, three hard cuts, one rig family between the hook and the run-in. Its
job is to isolate one variable: how much of V28's problem was the cutting.

| from | to | s | rig | racers | pack on screen | cut on |
|---|---|---|---|---|---|---|
| 0.02 | 2.23 | 2.22 | `hook_release` | 93 px | 96% | release |
| 2.23 | 9.02 | 6.78 | `chase_rear_3q` | 95 px | 80% | drum first contact |
| 9.02 | 12.68 | 3.67 | `chase_rear_3q` | 92 px | 74% | pair first contact |
| 12.68 | 19.15 | 6.47 | `finish_chase` | 77 px | 85% | last first contact |

The second shot carries the drum, the second hairpin, the sweep and the approach
to the pair in one take - four of the course's beats, none of them cut to.

## 8. Camera B - racing broadcast hybrid

Five shots, four hard cuts, four different rigs. Variety bought from rig changes
at motivated cuts rather than from cutting more often.

| from | to | s | rig | racers | pack on screen | cut on |
|---|---|---|---|---|---|---|
| 0.02 | 2.23 | 2.22 | `hook_release` | 93 px | 96% | release |
| 2.23 | 6.28 | 4.05 | `chase_rear_3q` | 100 px | 87% | drum first contact |
| 6.28 | 9.02 | 2.73 | `chase_side` | 90 px | 65% | sweep first contact |
| 9.02 | 12.68 | 3.67 | `bend_orbit` | 89 px | 68% | pair first contact |
| 12.68 | 19.15 | 6.47 | `finish_chase` | 77 px | 85% | last first contact |

## 9. Camera C - low pursuit

Six shots, five hard cuts, the lift pulled 1.6 units under the rail throughout
and the reach at its floor. Larger racers, stronger foreground, less of what is
coming.

| from | to | s | rig | racers | pack on screen | cut on |
|---|---|---|---|---|---|---|
| 0.02 | 2.23 | 2.22 | `hook_release` | 93 px | 99% | release |
| 2.23 | 4.58 | 2.35 | `chase_pack` | **108 px** | **100%** | drum first contact |
| 4.58 | 6.28 | 1.70 | `chase_side` | 98 px | **52%** | drum last contact |
| 6.28 | 9.02 | 2.73 | `compression_follow` | 100 px | 68% | sweep first contact |
| 9.02 | 12.68 | 3.67 | `chase_pack` | 96 px | 68% | pair first contact |
| 12.68 | 19.15 | 6.47 | `finish_chase` | 79 px | 82% | last first contact |

C's `drum_low` is the best single shot in the session by these numbers - 108 px
with the whole active pack on screen for every frame of it - and its
`pan2_side`, two shots later, is the worst at 52%. That spread is C.

---

## 10. Cut metrics

`docs/validation/race2/v281_camera/compare.json`, all four measured by the same
instrument over the same replay.

| | V28 | A | B | C |
|---|---|---|---|---|
| shots | 11 | **4** | 5 | 6 |
| hard cuts | 10 | **3** | 4 | 5 |
| mean shot | 1.74 s | **4.78 s** | 3.83 s | 3.19 s |
| shortest shot | 0.93 s | 2.22 s | 2.22 s | 1.70 s |
| longest shot | 3.78 s | **6.78 s** | 6.47 s | 6.47 s |
| share in the two longest takes | 36% | **69%** | 55% | 53% |
| share in takes of 3 s or more | n/a | **88%** | 74% | 53% |
| screen-direction reversals | **5** | 0 | 0 | 0 |
| racers, 1080 frame | 57.5-85.2 px | 77.4-95.4 | 77.4-99.8 | **79.0-108.5** |
| racers, 270 frame | 14.4-21.3 px | 19.3-23.8 | 19.3-25.0 | **19.7-27.1** |
| peak lens speed | 72.0 u/s | 45.6 | 45.6 | **40.0** |
| peak lens turn rate | 189 deg/s | 111 | 111 | 129 |
| minimum lens clearance | **-6.60 u** | **5.64 u** | 5.20 u | 4.15 u |
| **FLOW** | **24.3** | **85.5** | 77.9 | 70.2 |

FLOW is a weighted sum of five of the brief's own criteria - continuity 40,
cut budget 15, reacquisition 20, screen direction 15, scale 10 - and it is not
claimed to be quality. It is a regression detector and a way of ranking an
obviously disruptive edit against an obviously smooth one. Every term is
reported separately above so a number that disagrees with the picture can be
taken apart rather than argued with.

## 11. Reacquisition

At every cut: how far the active pack's centroid moves in normalised screen
space, where 1.0 is half the frame width, and how much its apparent size changes.

| | V28 | A | B | C |
|---|---|---|---|---|
| worst pack jump | **1.784** | 0.285 | 0.285 | 0.309 |
| worst scale change | 1.33x | 1.19x | **1.18x** | 1.33x |
| worst lens-angle change | 123.7 deg | **10.3 deg** | 19.5 deg | 26.9 deg |

Per shot, the fraction of active-pack samples outside the frame width and behind
geometry - the two measures V28's anticipation shots fail on:

| | worst shot, out of frame | worst shot, occluded |
|---|---|---|
| V28 | 58.5% (`sweep_anticipate`) | 56.2% (`sprint`) |
| **A** | **19.6%** (`middle`) | **6.6%** (`upper`) |
| B | 19.9% (`sweep_out`) | 12.4% (`pair_bend`) |
| C | 23.2% (`sweep_low`) | 34.0% (`pan2_side`) |

Both candidates' openings are measured at **0.0% out of frame** - the shot that
was the worst in the build before the feed-forward is now the best.

Every candidate's worst cut is inside the 0.33 reference - the width of the pack
itself at these shot sizes - so the racers overlap their own outgoing position
and there is nothing to re-find. V28's worst is five times that.

## 12. Phone review, at 270x480

`exports/race2_v281_cinematography/phone/`, scaled down from the delivered file
rather than rendered natively, because that is what a phone actually does to the
file it is sent.

The key question is the brief's: *can I keep watching my chosen colour without
re-searching for it after every camera transition?*

- **V28: no.** Five screen-direction reversals and a 1.78 half-frame jump at the
  worst cut mean the eye is re-acquiring on most of eleven cuts, and at 14.4 px
  the colours are at the legibility floor while doing it.
- **A, B and C: yes.** Three to five cuts, none of them moving the pack more than
  a third of a half-frame, no reversals, and 19.3-26.3 px of marble. The opening
  frame reads all eight colours distinctly at 270 px wide, which is the PICK A
  COLOUR promise being kept rather than asserted.

## 13. The final sprint

Identical in all three by construction - one `finish_chase` take from the last
powered mechanism to the end of the film.

| | |
|---|---|
| | A and B | C | V28's last shot |
|---|---|---|---|
| duration | **6.47 s** (12.68 to 19.15) | 6.47 s | 3.78 s |
| hard cuts inside it | **0** | 0 | 0 |
| top three visible | **82.7%** of frames | 80.2% | 74.6% |
| winner visible | **96.7%** of frames | 94.6% | 100% |
| winner size | 73.2 px mean, 58.4 px worst | 74.5 / 59.3 | 77.0 / 76.4 |
| visible before the crossing | **2.92 s** | 2.78 s | **0.45 s** |
| identical frame pairs | 0 | 0 | 0 |

V28's own last shot scores well on the columns it is measured on and is
disqualified by the one that matters: it is the `payoff`, it starts 0.45 s
before the line, and the comeback that decides the race happens in the two
shots before it.

It contains the last wheel, m7 taking the lead at 13.12, m2 taking it back at
14.38, m7 taking it again at 15.57, the 0.067 s crossing at 15.82 and all eight
racers home by 18.75 - without a cut. The comeback is watched rather than
reported.

## 14. Against V28

Answering the brief's review questions directly, against the rendered films.

1. **Can I continuously follow one colour?** V28, no: five reversals and a 1.78
   half-frame jump. A/B/C, yes: zero reversals, worst jump 0.31.
2. **Do I understand where the race is going?** Better. The aim leads toward the
   course ahead wherever that does not cost the racers their place in frame.
3. **Does the camera travel with the race?** This is the whole architectural
   change: the lens rides an arc length rather than being placed near a station.
4. **Do mechanisms appear naturally ahead?** Yes, and without a shot of their
   own - A covers four beats in one take. V28 gave each an anticipation cut, and
   those shots spend 41-52% of their samples with the pack out of frame.
5. **Do I see consequences after impacts?** Yes - the take continues through
   them rather than ending on them.
6. **Do cuts preserve spatial orientation?** Yes: zero reversals against five.
7. **Does the race feel fast?** Better: racers are 33-50% larger and the lens
   moves with them rather than waiting for them.
8. **Cinematic rather than game-replay?** Better, with the caveat in section 16.
9. **Does the final sprint feel like one contest?** Yes - it is one 6.47 s take.
10. **Does any camera movement call attention to itself?** The opening's quarter
    turn is the only move a viewer will notice, and it is motivated by the
    release. Peak lens speed is 40.6 u/s against V28's 72.

## 15. The winner: **camera A, continuous chase**

Against the brief's stated priority order:

| priority | winner | why |
|---|---|---|
| 1. race continuity | **A** | 3 cuts, 69% of the film in two takes, 88% in takes of 3 s or more |
| 2. following a chosen colour | A = B | worst pack jump 0.285 for both |
| 3. spatial orientation | A = B = C | zero reversals for all three |
| 4. final sprint | A = B = C | identical 6.47 s take |
| 5. anticipation | A = B | B's side pursuit reveals the pair better; A's long take reveals the sweep better |
| 6. racer size | C | 79-108 px, but see below |
| 7. cinematography quality | B | the only candidate with real rig variety |
| 8. visual excitement | C | lowest and closest |

**A wins on the first criterion by a wide margin and is not beaten on any of
the first four.** That settles it under the brief's own ordering: 69% of the
film inside two takes against B's 55% and C's 53%, and 88% inside takes of three
seconds or more against 74% and 53%.

The brief expected B. B is a good film and it is the better *showreel* - the
side pursuit across the sweep's consequence is the best single shot in the
session, and at t=8.0 B holds the racers where A has lost them. But B buys that
with a third more cutting, and the thing this branch exists to fix is the
cutting. **The honest reading is that A wins the experiment and B wins the
craft**, and the recommendation in section 17 follows from that rather than
pretending the gap is larger than it is.

**C is falsified as a direction, usefully.** Its lower lift costs clearance
(4.15 units against A's 5.64), it is the only candidate whose worst scale jump
reaches V28's, and its six shots put it back within one cut of the failure being
repaired - for 13 px of marble. The switchyard's own geometry is why: the legs
are 9.6 layout units apart, so a lens closer than about nine units laterally
must rise to clear the next leg, and rising makes it the plan view. **The fold
sets a floor on camera distance and therefore a ceiling on racer size**, and C
is the measurement of where that ceiling is.

## 16. Remaining weaknesses

1. **The frame is half empty, and this branch did not fix it.** The V26
   environment is a dark valley and a portrait frame of a compact course leaves a
   lot of unlit rock. The brief rules it out of scope and the other session owns
   it. It is the single biggest difference between these frames and a finished
   film, and it is the reason the rendered stills read sparser than the metrics
   suggest.
2. **A loses the pack around 8.0 s**, between the sweep and the pair, where B's
   side pursuit holds them. It is the clearest single argument for B and the
   first thing to fix in A - most likely by giving the long take a rig that leans
   further out across that stretch rather than by cutting.
3. **C's `pan2_side` is occluded on 34% of its samples** - the only shot in any
   candidate that is worse than the V28 average on that measure. A side rig at a
   1.6-unit negative lift on the second hairpin is standing too low to see over
   the pan it is beside. It is C's problem and it is part of why C loses.
4. **Up to 23% of active-pack samples are outside the frame width** on the worst
   shot of each candidate (A 19.6%, B 19.9%, C 23.2%), against V28's 46.7-58.5%
   on its anticipation shots. Not zero, and the honest cost of `PACK_MAX` = 4
   framed at a readable size.
5. **The flow score is a regression detector, not a judgement.** It ranks these
   four correctly and it should not be quoted as a quality number.
6. **Only one seed is filmed, and only one course exists.** The schedules are
   authored against race markers rather than times, so they should transfer, but
   nothing here proves it on a second seed. And every Race #2 course shares one
   centreline, so the reusability of the spine and rail is argued from their
   construction rather than demonstrated (section 4.2).

## 17. Recommendation

**Take camera A as the shipping camera and B's `chase_side` as the fix for
weakness 2.** They are the same seven rigs over the same rail; the difference is
four lines of schedule. A five-minute experiment - give A's long take a
`chase_side` lean across the sweep-to-pair stretch instead of holding
`chase_rear_3q` - would very likely produce the film that wins on both counts,
and it needs no new machinery.

Then, in order:

1. **Render the winner in the contained hall** as soon as the other session's
   stage lands. Weakness 1 is most of what stands between these frames and a
   deliverable, and the camera is environment-independent by construction -
   `tests/test_race2_cinematography.py` asserts that nothing in `race2.spine`,
   `race2.rig`, `race2.cinematography` or `race2.flow` reads an environment.
2. **Prove the schedules on a second seed**, and the rail on a second *plan*.
   The first is a flag. The second needs a course that is not built on the
   switchyard skeleton, and until one exists the reusability claim stays an
   argument rather than a measurement.
3. **Only then tune the opening** (weakness 3).

---

## Where everything is

| | |
|---|---|
| flow metrics, per candidate | `docs/validation/race2/v281_camera/flow_{A,B,C}.json` |
| the comparison | `docs/validation/race2/v281_camera/compare.json` |
| camera tracks | `output/race2/v281_camera/<CAM>/race2_switchyard_8.cameras.json` |
| **the control** | `exports/race2_v281_cinematography/race2_v281_V28.mp4` |
| **camera A** | `exports/race2_v281_cinematography/race2_v281_A.mp4` |
| **camera B** | `exports/race2_v281_cinematography/race2_v281_B.mp4` |
| **camera C** | `exports/race2_v281_cinematography/race2_v281_C.mp4` |
| side by side | `exports/race2_v281_cinematography/compare/V28_vs_{A,B,C}.mp4` |
| 4-up, per section | `exports/race2_v281_cinematography/compare/fourup_*.mp4` |
| section clips | `exports/race2_v281_cinematography/sections/<CAM>_<section>.mp4` |
| phone proofs | `exports/race2_v281_cinematography/phone/` |

`output/` and `exports/` are not in git, per this repository's convention.

## Tests

`tests/test_race2_cinematography.py`, 27 tests in two halves.

**The locks**, asserted against literals written in the test rather than
recomputed from the code under test: the hero seed's finish order, winner,
starting bay, margin, first and last finish, lead-change count, the five
mechanism contact times, the race runtime, the course's length, drop and station
list, that every candidate's frames are consecutive replay frames with nothing
omitted, that Race #1 is untouched, and that no camera module reads an
environment.

**The camera**: the spine's derived downhill azimuth, the rail's clearance and
continuity, determinism of the whole track, the active-pack rule as a pure
function, the 4-6 shot budget, the minimum shot length, that every cut lands on
a mechanism contact, that the final sprint has no cut in it, pack visibility and
racer size, lens clearance, lens speed, that the spring is actually critically
damped and its half-life is a half-life, that all three candidates cover the same
window, the identical-frame detector, and that the staged V28 control is byte
for byte the file V28 produced.

The camera-speed bound is anchored to **V28's own measured peak** (72.0 u/s,
189 deg/s) rather than to an invented number, because the brief asks for
kinematics as a diagnostic and "no faster than the camera being replaced" is the
one threshold that is not made up. The candidates peak at 45.6 u/s and 129
deg/s, both during the opening swing.

**28 passed, and 72 Race #2 tests pass together** - the 44 that existed before
this branch, unchanged.
