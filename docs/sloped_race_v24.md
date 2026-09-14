# V24: the first scroll decision

The first Short went up as V22.1. It was watched almost to the end by the people
who watched it at all, and four viewers in five never got that far.

| | |
| --- | --- |
| stayed to watch | **19.6%** |
| swiped away | **80.4%** |
| average view duration | ~24 s |
| video duration | ~27 s |
| average viewed | **~89%** |

Those two numbers point in opposite directions and only one reading fits both.
Nobody who stayed got bored - 89 per cent of a 27-second film is most of the
race, including the slowest parts of it. What failed is the **first scroll
decision**: the thing a thumb makes in under a second, before the premise has
arrived.

So V24 is a controlled experiment with one variable, and the variable is *what
is on screen at second zero*.

---

## 1. What the shipped opening spent its first four seconds on

Measured on the delivered file rather than described:

```
OUTPUT  0.000 - 3.500   a course preview: an aerial flight over an empty
                        hillside. No racer is on screen at all
OUTPUT  3.500 - 4.200   the first race frame, frozen, under PICK ONE
OUTPUT  4.200           the film starts moving
```

On the frame the hold freezes, the eight racers are **81.3 px** across on a
1080x1920 delivery, **2.01 per cent** of the picture by area, 0.34 off centre,
and **78.2 per cent** of the frame is distant hillside and sky. A cold viewer's
first sight of a racer is four and a fifth seconds in, at two per cent of the
frame, not moving.

## 2. The controlled test

V24 keeps the race and changes the opening, the length and the end card.
Everything else is held fixed *on purpose*, so that a second upload's numbers
can be attributed:

| held fixed | changed |
| --- | --- |
| seed 5432, the locked replay, PyBullet | no course preview |
| finish order 5, 2, 7, 4, 1, 6, 3, 0 | no frozen opening hold |
| winner marble 5, PURPLE | a hook camera live from frame zero |
| the course, the obstacle, the fork | PICK A COLOR over live footage |
| the V22.1 chase, finish and grade | ~20 s instead of 26.5 |
| the V22.1 environment - **no V23** | visible marble rotation |
| every racer colour | a payoff that names the colour |

The V23 Aurora Valley and the v23b machine palette are deliberately **not**
here. They remain on `v23-integration` as the next experiment; putting them in
this one would make the result unattributable.

Countries are not here either, for the same reason. The question this pass asks
is whether an immediate colour-selection hook fixes swipe-away, and a country
skin is a different question.

---

## 3. The hook

`b_gate` of the hook lab: the front three-quarter across the gate row, opening
at extent 7.2 and pulling back onto `v221.START`'s own first pose over 1.4 s.

Measured on the integrated film's own frame zero, which reproduces the lab's
proof to two decimal places:

| | shipped V22.1 | **V24 / b_gate** |
| --- | --- | --- |
| racers in frame | 8/8 | 8/8 |
| racers in their own colour, 1080x1920 | 8/8 | 8/8 |
| the same, at 270x480 | 8/8 | 8/8 |
| median racer | 81.3 px | **146.2 px** |
| smallest / largest | 79 / 84 | **129.8 / 167.3** |
| racer share by area | 2.01% | **6.61%** |
| off centre | 0.34 | **0.08** |
| off centre, sideways | 0.35 | **0.00** |
| least-visible disc | 0.99 | 0.84 |
| closest pair, diameters | 0.97 | 0.71 |
| frame is racer + machine | 16.6% | **34.5%** |
| frame is distant hill + sky | **78.2%** | **8.2%** |
| first mechanism motion | 4.47 s | **0.117 s** |
| first camera motion | never | **0.167 s** |
| first racer motion | 4.47 s | **0.233 s** |

Three things the front angle gets that no rear framing does: the module's
backboard is *behind* the racers rather than crossing them; the course's own
**START sign** is in the picture, which is the cheapest statement of the premise
there is and was already built; and the backdrop is the massif in shade rather
than the sunset, which is what collapses the empty share and puts the mark back
at the top of the frame.

### 3.1 PICK A COLOR

`PICK A COLOR`, not `PICK ONE`. Twelve glyphs at 96 pt with the film's own
tracking is 798 px - a thirteen per cent margin each side - and 71 px of cap
height, which is **17.8 px at 270x480**. The baseline is **269**, at the top of
the frame above the START sign, which is where `v24_hook.text_plate` scored the
best of 37 candidate bands on the rendered picture.

It is up at **output 0.000** and starts to leave at 1.05, gone by 1.30.

**There is no fade in.** A `fade=t=in` starting at second zero makes the first
frame transparent, and the first frame is the one this whole pass exists for.
`tools/sloped_short.py` omits the filter when the mark opens at zero and keeps
it for every edition that opens its mark over a held frame; a test reads the
filter graph for both.

### 3.2 The hook camera, reviewed rather than accepted

The brief flagged the reveal as possibly a whip. Measured on the integrated
track:

```
frames        85          peak step   0.6475 layout units/frame at frame 63
median step   0.2899      first 10 frames   0.001 to 0.025
```

The move is back-loaded by `lead=1.5`: the first sixth of it is nearly still,
which is the tight framing being dwelt on, and the peak is two thirds of the way
through. **0.6475 is under `chase_camera.MAX_LENS_STEP`, which is 0.85** and is
the per-frame lens ceiling the film's own chase shots are held to. It was left
at 1.4 s rather than eased toward the lab's 1.85 s ceiling, because the premise
has to read instantly and the number is already inside a production bar.

### 3.3 The landing

The hook's last row **is** the start shot's first row - not close to it, the
same row - so the two are concatenated with no join at all.

```
lens step across the handoff   0.0361 layout units
aim step                       0.0032
field of view step             0.0000
shared row matches             yes
```

---

## 4. The timeline

No preview, no hold, three omissions, one truncation. Every segment slope 1.

| cut | replay | output | frames |
| --- | --- | --- | --- |
| hook | 0.2000 - 1.6000 | 0.0000 - 1.4000 | 85 |
| start | 1.6000 - 2.0500 | 1.4000 - 1.8500 | 27 |
| *the mixer omission* | *2.0500 - 4.4833* | | *145* |
| start | 4.4667 - 6.4167 | 1.8500 - 3.8000 | 117 |
| *the fall, on the lens change* | *6.4167 - 6.7167* | | *17* |
| descent | 6.7000 - 9.6667 | 3.8000 - 6.7667 | 178 |
| obstacle | 9.6667 - 13.5833 | 6.7667 - 10.6833 | 235 |
| *the spinner trap* | *13.5833 - 14.0333* | | *26* |
| obstacle | 14.0167 - 15.1000 | 10.6833 - 11.7667 | 65 |
| fork | 15.1000 - 16.7333 | 11.7667 - 13.4000 | 98 |
| branches | 16.7333 - 18.4167 | 13.4000 - 15.0833 | 101 |
| merge | 18.4167 - 18.9000 | 15.0833 - 15.5667 | 29 |
| final | 18.9000 - 23.4500 | 15.5667 - 20.1167 | 273 |

**Final runtime: 20.133 s, 1208 frames.** The pacing lab's Candidate B
prototypes 19.867. V24 is 0.266 s longer, and the difference is not one
decision but three, each made on a measurement:

```
Candidate B                                       19.867 s
+ 0.483   STOPPED and ANTICIPATION dropped        section 5.1
+ 0.067   the trap resumes 4 frames earlier       section 5.4
- 0.700   no frozen hold
+ 0.450   the tail runs as long as the card does  section 6.2
- 0.033   whole-frame arithmetic
                                                  20.133 s
```

The brief's preferred band is 18.5-20.5 and its stated priority is that visible
continuity beats staying under 20.000. Every second above Candidate B was bought
by a continuity or legibility measurement, and none of it is slack.

### 4.1 Why `presentation.omit_frames` is not used

The pacing lab found that it emits **one segment per window of the edit map**,
which is right for every cut production has ever made and wrong for a cut in the
middle of a window: the surviving replay is compressed into one segment at slope
1.43 and every frame after it is mis-dated by up to 0.5 s.

V24 does not work around that and does not fix it. It does not need either,
because a re-render can make an omission a **window boundary**, which is what an
omission is. `EDITIONS["v24"]["cuts"]` is empty, the master is rendered to the
film's own length, and a test pins the helper's limitation so the workaround can
go when it is fixed.

### 4.2 Why the camera is re-solved and not frame-selected

The pacing lab warned that cutting the delivered master leaves a camera
discontinuity, because V22.1's constant-rate legs were solved against V22.1's
windows: dropping 28 more frames steps the lens 28 frames' worth of its own
orbit, **1.56 layout units**, where an ordinary frame steps 0.054.

V24 re-solves the start to its own windows. `v221_shuffle.constant_rate_legs`
already splits a move across however many windows it is given, so the orbit runs
`-23.7 -> +4.0` over V24's 2.400 s instead of `-36.0 -> +4.0` over V22.1's
4.550 - the same arc, ending on the same pose, spent in the time V24 has.
Measured on the integrated track:

```
join                    camera step   an ordinary frame of that shot
hook  -> start             0.0721            0.0361
start -> start (mixer)     0.0707            0.0708      <- one frame
start -> descent          19.3301            0.0651      <- the lens change
obstacle -> obstacle       0.6926            0.1831
```

**The mixer join steps the lens by one ordinary frame.** That is the whole
argument for a re-render in one number.

The body is not re-solved, because it does not need to be: the chase is a
function of replay time and its bounds are unchanged. **986 body rows are
byte-identical to `cameras_v221_5432.json`**, which a test asserts as equality
rather than tolerance.

---

## 5. Visible marble rotation, and the finding that moved a cut

`--racers=meridian`. The marker is painted into the racer material's albedo map,
which lives in the mesh's own UV space and is therefore carried by the node
transform the replay already sets: no child node, no second transform, no
synthetic spin law, nothing derived from linear speed. `solid` remains the
scene's default, so every earlier edition re-renders what it shipped.

The replay already contains the rotation. Representative angular speeds:

```
mixer     median  2.12 rad/s   p95 16.98   max  26.49
release   median 15.51         max 49.94
descent   median 87.28         max 154.25
```

A uniformly coloured sphere is invariant under every rotation, so all of that
produced **exactly 0.0** visible surface change on every pair of frames in the
shipped film. Meridian makes it observable - and observable cuts both ways.

### 5.1 The criterion that inverted

The pacing lab chose three of Candidate B's five omissions by **churn**: the
deadest stretches in the film, where the marbles travel least per second. That
is exactly right for a plain sphere and exactly inverted for a marked one,
because a rotation cut is hidden by *motion*.

Every join, measured as the median visible-face change across it against the
95th percentile of the per-frame visible-face change of **the shot it sits in**:

| join | omitted | turn, median | visible change | its shot's p95 | ratio |
| --- | --- | --- | --- | --- | --- |
| `SPIN` mixer | 2.433 s | 119.2° | 0.260 | 0.220 | **1.18** |
| `STOPPED` rotor halted | 0.283 s | 24.9° | 0.220 | 0.046 | **4.8** |
| `ANTICIPATION` pre-release | 0.200 s | 12.3° | 0.157 | 0.052 | **3.0** |
| `FALL` on the lens change | 0.283 s | 103.6° | 0.237 | 0.189 | **1.26** |
| `TRAP` spinner | 0.433 s | 147.2° | 0.249 | 0.183 | **1.36** |
| *V22.1's own shipped mixer join* | *1.950 s* | *119.7°* | *0.258* | *0.220* | *1.2* |

**The two cheapest cuts in the film on churn are the two most exposed cuts in it
on marking, by a factor of three to five.** The mixer - where a marble turns 119
degrees across the join, which sounds like much the worst of them - is the
safest, because in the mixer a marble turns 1.8 degrees every ordinary frame and
the picture is already a blur of tumbling. On the stopped rotor an ordinary
frame turns a marble 1.5 degrees, and a marble that holds its place on screen
while its marking rotates 25 degrees is the only thing in shot that moved.

So `STOPPED` and `ANTICIPATION` are **not in V24**. Their 0.483 s is given back,
which is where V24's runtime is 0.266 s over Candidate B's.

The bar is `EXPOSURE_BAR = 1.5`, and it is not a round number: it is where the
film's own accepted joins fall. V22.1's shipped mixer omission - the one join a
real audience has watched without reporting - measures 1.2, and the
start-to-chase lens change, which *is* a cut and is supposed to be visible,
measures 1.26.

### 5.2 The mixer join was left in one continuous camera, and why

The brief's suggested grammar was hook → close mixer angle → second mixer angle
→ chase, putting the big temporal omission on a deliberate camera cut. The
measurement says it does not need one, and adding one would cost something real:
V22.1's b116 join is phase-locked to a hundredth of a degree *and* carries the
camera's position and velocity across, and a cut would throw both away to solve
a problem that measures 1.18.

The one omission that does sit on a camera cut - `FALL` - is there because the
film already cuts there.

### 5.3 The rotor phase, from the rendered frames

The renderer draws each cut's rows and drops the **first** row of every cut after
the first, so a window written `from 4.000` first appears at 4.016667. That is
why V22.1's b116 join is one frame off its own nominal lock: it asks for four
exact revolutions and renders one more frame of them, so the blades step 24.86
degrees where a frame step is 12.41.

V24 resumes 28 rendered frames later, which makes the rendered gap 146 frame
steps - 145 of them five exact revolutions:

```
blades step across the mixer join   12.46 deg
one frame of that spin              12.41 deg
phase error                          0.04 deg     (V22.1 ships 12.44)
```

**V24's mixer join is more phase-exact than the join it extends.**

### 5.4 The mechanism nobody had ever checked

`v24_spin.MACHINE_KEYS` is `start.rotor0..3`. That is the correct constraint for
a cut inside the start shot, and it is the only one any pass before this one
checked a candidate cut against.

The spinner trap's cut is not in the start shot. Its subject is
`obstacle.wheel0..2` - three four-bladed wheels the field is being held against -
and nobody had them in a check. Measured with the near edge fixed and the far
edge slid a frame at a time, against the wheels' own 90-degree symmetry:

| resume | omitted | blades step | phase error | marbles move |
| --- | --- | --- | --- | --- |
| 14.0167 | 25 f | 89.38° | 4.06° | 0.820 units |
| **14.0333** | **26 f** | **92.82°** | **0.62°** | **0.859** |
| 14.0833 | 29 f | 103.13° | 9.69° | 0.974 |
| 14.1000 | 30 f | 106.57° | **13.13°** | 1.013 | *(the pacing lab's)* |

One frame of blade step is 3.44 degrees, so the lab's placement puts **3.8
frames of blade rotation into a single frame** on the one mechanism the shot is
looking at. V24 resumes four frames earlier and lands at 0.62 degrees - better
on the blades by a factor of twenty-one and better on the marbles as well, for
four frames of runtime.

`tools/sloped_v24_audit.py` now reports every rotating family across every join
and flags which one is on screen, so the next pass cannot check the wrong
machine.

### 5.5 The orientation-join audit

Full rows are in `docs/validation/sloped_race_v1/v24_integration/joins.json`.

| | `spin` | `fall` | `trap` |
| --- | --- | --- | --- |
| replay before | 2.0500 | 6.4167 | 13.5833 |
| replay after | 4.4833 | 6.7167 | 14.0333 |
| output at | 1.850 | 3.800 | 10.683 |
| camera | `start` -> `start` | `start` -> `descent` | `obstacle` -> `obstacle` |
| same camera or a cut | same | **cut** | same |
| camera step | 0.0707 | 19.3301 | 0.6926 |
| field of view | 34 -> 34 | 34 -> 36 | 36 -> 36 |
| turn, median / worst | 119.2° / 168.1° | 103.6° / 156.1° | 147.2° / 176.4° |
| screen move, median / worst | 32.8 / 101.2 px | 179.6 / 261.9 px | 60.1 / 151.5 px |
| visible change, median / worst | 0.260 / 0.326 | 0.237 / 0.321 | 0.249 / 0.334 |
| shot's own p95 | 0.220 | 0.189 | 0.183 |
| **exposure** | **1.18x** | **1.26x** | **1.36x** |
| mechanism on screen | `start.rotor` | `start.rotor` | `obstacle.wheel0..2` |
| its phase error | **0.04°** | 0.00° | **0.62°** |
| machine state either side | identical | identical | identical |
| verdict | inside the churn | the cut is the edit | inside the churn |

Every machine-state reading - rotor rate, panel height, paddle height - is
identical across all three joins to four decimal places, so no cut straddles a
gate, a rotor ramp, a blade lift or the trapdoor.

---

## 6. The payoff

`plate` of the payoff lab. **PURPLE WINS** over **6TH -> 1ST**, with the word
reversed out of a lozenge of the winner's exact `#8E3FD4`.

The winner is marble 5, reproduced twice by the lab - once by re-running the
race on `sloped_course(routes="both")` and once from the locked replay's finish
events - and pinned by test here against the replay the film ships. The default
machine has no fork and returns a different winner entirely.

```
warm white on the plate   5.26 : 1
purple text on the tail   poor - which is why the plate is the colour sample
colour area               56 088 px, about 23x the shipped card's dot
ink box                   y 322 - 523
```

### 6.1 The band, re-measured

The payoff lab measured a dark band at y 297-548 over a tail that ran to replay
24.467. V24's stops at 23.450, so it was re-measured rather than inherited:
every second frame of V24's own tail, on the **silent** master so no overlay is
in the reading, taking each row's maximum luma across the text corridor.

```
tallest run whose maximum never exceeds 130   y 296 - 548, 253 px
worst luma inside it                          129.9
worst luma over the card's own ink rows       122.2
```

One row taller than the lab's y 297-548 and otherwise identical, because this is
the same parked stand shooting less of the same thing. The card's ink at
y 322-523 sits inside it with 25 px of margin above and below.

### 6.2 The ring, and where the tail's length comes from

V22.1 opened its ring 0.200 s after the crossing and ran it 0.700 s, which the
lab measured put **one frame of 42** on a visible marble; the rest was a gold
circle on the gantry rail with the second-place emerald inside it.

V24 opens the ring **on** the crossing and runs 0.300 s. Measured on the
finished file by counting the winner's own hue inside its projected disc:

```
ring window            output 17.517 - 17.817, 18 frames
before the ring        ~1800 purple px, the marble arriving
the opening flash      2 frames, the marble washed to warm white
under the ring         11 frames, 1200-1840 purple px
the rail takes it      0.217 s after the crossing
```

So **13 of the ring's 18 frames are on the winner and 11 of them show it in its
own colour**, against one frame of 42. The two flash frames are `winner_ring`'s
own designed beat, synchronised with the crossing cue; at 60 Hz a 33 ms
highlight reads as a flash rather than as the ball changing colour.

The tail is then **derived, not chosen**:

```
20.850   the winner crosses
+ 0.800  the recognition beat, the bottom of the lab's 0.8-1.5 s band
+ 1.800  the card's own length, long enough to read two lines twice
= 23.450  which is 0.050 s short of the sixth crossing at 23.500
```

On the finished film that is the winner crossing at output **17.517**, the ring
at 17.517-17.817 and the card at **18.317-20.117** against a 20.133 s film: five
marbles arrive, the film ends one frame after the card does, and no sixth is
caught half way down the channel by the last frame. Candidate B's
23.000 would have left the card 1.267 s, under the length the lab measured it
needs; 0.450 s is what that costs.

---

## 7. Audio

The architecture is unchanged and nothing was redesigned; the retiming follows
the new edit map, because every cue derives its position from the clock.

V24 uses V22.1's cue policy: **no whoosh on the omissions** - all three are
continuous in the picture, and a whoosh over an invisible join announces an edit
nobody could otherwise see - and the mixer's own machinery, since V24 still
holds 1.95 s of drum on screen.

```
placed      ambience, rolling, gate, tension, trapdoor, mechanism, lift,
            206 impacts, 2 splits, 5 crossings, music
peak in     -10.46 dBFS   compressor 5.19 dB   out -1.46 dBFS   limiter idle
integrated  -13.90 LUFS   range 3.70 LU   true peak -1.51 dBTP
```

The winner's crossing is the loudest crossing by 2.9 dB over the next one
(-1.48 against -4.35) and 7.6 dB over a typical mid-race moment, and the
limiter never engages - so the hierarchy in the finish is the designed one
rather than one a compressor flattened.

There is no outro sting. The winner accent is the loudest moment in the film and
lands on the crossing, which is the same frame the ring opens on.

---

## 8. Phone review

At 1080x1920 and at 270x480:

| | |
| --- | --- |
| frame 0, all eight colours distinguishable | **yes**, 8/8 at both sizes |
| PICK A COLOR immediate | **yes**, full opacity on frame 0, 17.8 px cap at 270x480 |
| something moving | **yes**, the paddles at 0.117 s, the lens at 0.167 s |
| does the first second stop the scroll | the eight balls, the START sign and the words are all there before anything else happens |
| mixer, rotation visible | **yes** - the markers are legible on the drum at 270x480 |
| do the temporal cuts make the markings teleport | no: the mixer join is indistinguishable from its neighbours in a six-frame strip |
| release satisfying | the floor opens at 3.500 s with 1.5 s of visible wind-down in front of it |
| race coherent | the body is V22.1's picture unchanged |
| purple identifiable at the finish | **yes** - it arrives purple, flashes for two frames, and is ringed in its own colour |
| PURPLE WINS / 6TH -> 1ST readable | **yes**, 5.26:1 on a band whose worst pixel is 129.9 |

Sheets: `docs/validation/sloped_race_v1/v24_integration/compare.png` and
`compare_phone.png`, both in the branch.

The opening comparison clip - the single most useful artefact in the pass, five
seconds of each film side by side - is `opening_v221_vs_v24.mp4`. `*.mp4` is
gitignored, as it has been since V19, so it and the three delivered files live
in `exports/v24_integration/` rather than in the branch.

---

## 9. Tests and QC

`tests/test_sloped_v24_integration.py`, 36 cases, alongside the four labs'
own suites which all still pass unchanged.

Covered: the seed, the digest and the finish order; the winner is marble 5 and
it is PURPLE; nothing writes to the replay; the recorded quaternions are unit
and turning, and `racer_visual.gd` contains no `_process`, `Time.`, `Tween`,
`AnimationPlayer` or `rotate(`; no preview; no hold; `b_gate`; PICK A COLOR and
no fade-in on its stream; frame zero's eight racers and their sizes; first
motion inside 0.25 s; every segment slope 1 and tiling; the obstacle split as
two windows; `omit_frames`' defect reproduced so the workaround is pinned; three
omissions and their measured bounds; the mixer's rendered phase lock; every
on-screen mechanism phase-clean and the rejected placement recorded; every join
under the exposure bar; 986 body rows identical to V22.1; the chase still opening
at `START_HANDOFF`; the start legs re-split; the hook landing on the start's own
row; five crossings; meridian selected and `solid` still the default; the plate,
the ring and the card's window; the runtime; and every historical edition's
fields untouched.

Short QC passes clean. Three checks were made edition-aware rather than
weakened - the hold is now `clock.hold_frames` rather than a constant, the ring
window is the edition's, and the mark-versus-machine rule is inverted for V24
because the mark now sits over live footage - and the hold check gained its own
mirror image:

```
[pass] the opening is live, not held: over 14 adjacent frames the median step
       is 3.4855 with 22.577% of pixels moved (a held frame is under 0.10 and
       0.500%)
```

That is `_hold_is_static`'s measurement, its window and its bars, asked the
opposite question, so a film cannot satisfy both and cannot slip between them.
New V24 checks: the mark's ink on frame zero, every join's exposure and phase,
the card's window, and the tail's dark band re-measured on the silent master.

---

## 10. Weaknesses

1. **The hook's peak camera step is 0.6475 units/frame.** Inside
   `MAX_LENS_STEP` and back-loaded, but it is the fastest lens move in the
   opening of any edition and it has not been watched by anyone but its author.
   The lab's ceiling of ~1.85 s is the lever if it reads as a whip.
2. **Two frames of the winner are washed white by the ring's flash.** By design,
   and on the marble rather than on a rail for the first time - but it is the
   frame that names the winner, and a softer flash is available.
3. **Five of eight crossings.** The 6th, 7th and 8th arrive after the film ends.
   The winner is the *first* crossing, so the result is never in doubt, but a
   viewer who picked marble 0 never sees it finish.
4. **The trap omission is still the least comfortable join in the film** at
   1.36x its shot's spread and a 0.69-unit camera step, which is 3.8 ordinary
   frames of lens travel. `TRAP_SHORT` would bring it down for 0.17 s of runtime.
5. **The two dropped omissions were not replaced.** `STOPPED` and
   `ANTICIPATION` were removed rather than moved to a camera cut, which is the
   other option the brief offered. A start with one deliberate cut in it might
   buy that 0.483 s back; it would also throw away b116's phase lock.
6. **`presentation.omit_frames` is still wrong** for an interior cut. V24 routes
   around it rather than fixing it, and a test pins the limitation.
7. **The retention hypothesis is untested.** Everything above is a measurement
   of the film, not of an audience.

---

## 11. The hypothesis for upload #2

> Removing the 3.5 s course preview and the 0.7 s frozen hold, and replacing
> them with a live frame-zero hook in which all eight racers are 146 px across,
> 6.6 per cent of the frame, centred, under the words PICK A COLOR, with the
> mechanism moving 0.117 s in - will move **stayed to watch** materially above
> 19.6 per cent.

The prediction it rests on: the ~89 per cent average-viewed figure holds or
improves, because the body of the race is the same body. If *stayed to watch*
rises and *average viewed* holds, the preview was the problem. If *stayed to
watch* rises and *average viewed* falls, the hook is writing a cheque the race
does not cash. If neither moves, the first scroll decision is not about the
opening shot at all, and the next variable to test is the one held fixed here -
the environment, on `v23-integration`.

---

## Files

```
sloped/v24.py                      the integration: windows, joins, the track
tools/sloped_v24_audit.py          the join audit, the first second, the sheets
tests/test_sloped_v24_integration.py

output/sloped_race_v1/v24/race_master.mp4        the silent render
output/sloped_race_v1/real_race_v24_master.mp4   no overlays, no audio
output/sloped_race_v1/real_race_v24_visual.mp4   overlays, no audio
output/sloped_race_v1/real_race_v24.mp4          the Short

exports/v24_integration/                         all of the above, plus the
                                                 comparison clip and this file
```

Rebuild:

```
python tools/sloped_v22.py   --edition v24 --stage all --godot PATH
python tools/sloped_short.py --edition v24 --stage all
python tools/sloped_v24_audit.py --stage all
```
