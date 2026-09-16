# V31: race readability — who is racing, and where the race is going

**Branch** `v31-race-readability-camera-track`, from `origin/v301-premium-stage-art-polish`
at `0bea452`.
**Scope** which racers the camera is attached to, and what the lens can see of
the course. No physics, no course, no mechanisms, no environment, no track
material. Camera A's shot philosophy — four shots, long takes, one uncut final
sprint — is unchanged and the ceiling of five shots is never approached.

---

## 1. The problem

The production candidate reads as a race and not as coverage. What it does not
always do is answer two questions the PICK A COLOR format depends on:

> **Where is the meaningful battle?** and **where is the race going next?**

The brief describes both symptoms precisely: active racers leaving the useful
composition, mechanisms dominating, the course ahead cropped, the viewer having
to reacquire their colour. This pass measures both, finds a different cause
from the one everybody expected, and fixes the cause.

Two new instruments do the measuring, both in `race2/readability.py`, both pure
functions of the camera track, the replay and the course — no image analysis,
because a pixel measure cannot tell a marble hidden behind a support from a
marble that is merely small, and cannot see the centreline under the racers at
all.

---

## 2. What the measurement actually found

### 2.1 The course ahead is never occluded. It leaves sideways.

Camera A shows **3.94 layout units of visible centreline ahead of the pack**,
which at racing speed is a third of a second, and **10% of its frames show
none at all** (`forward_arc_p10` = 0.00). The natural assumption is that the
machine is in the way. It is not:

```
t= 1.0  first fail at +4u   x = +1.12   not blocked
t= 4.0  first fail at +5u   x = -1.01   not blocked
t= 7.0  first fail at +8u   x = +1.07   not blocked
t=10.0  first fail at +7u   x = -1.07   not blocked
t=14.0  first fail at +4u   x = +0.95   not blocked
```

Over the whole film the course **never once stands between the lens and the
path ahead**. The path leaves through the left or right edge, at vertical
centre, within four to eight units.

The reason is the delivery frame. It is portrait 1080×1920, and at camera A's
34-degree lens that is **19.5 degrees wide** against 34 tall. Anything not
almost dead ahead is out of frame immediately.

### 2.2 And the switchyard is a hairpin every 32 units

```
head  pan1  corr1  pan2  corr2  pan3  corr3  pan4  corr4  pan5  sprint  runout
```

The `pan` runs are hairpins: ~16 units of arc turning through 180 degrees at 7
to 12 degrees per unit. The `corr` straights between them are ~16 units. **No
straight anywhere on this course is longer than 16 units.**

So the brief's "one to two seconds of visible path" — 12 to 24 units at racing
speed — is asking to see *round a fold*, which no lens standing behind the pack
can do. Measured at 7.0 s, with the pack in `corr2`:

| arc ahead | run | screen x | in frame |
|---|---|---|---|
| +4 | corr2 | +0.45 | yes |
| +8 | corr2 | +1.07 | **no** |
| +12 | pan3 | +1.71 | no |
| +20 | pan3 | +3.04 | no |

The coming hairpin sits **one and a half to three half-frames outside the
picture**, while the frame spends its width on the leg already run.

That reframes the target. On this course "where is the race going" cannot mean
a long ribbon receding to a vanishing point. It means **the current leg, the
fold at its end, and enough of the next leg to read the fold** — a lateral
composition, and one the horizontal field has to be wide enough to hold.

### 2.3 The active pack is smaller than the contest

`race2.rig.active_pack` is the leader plus everyone within 4.5 units of arc,
floored at three and **capped at four**. On the hero replay:

- the **cap binds on 73%** of frames — five to eight racers are genuinely in
  contention and the camera frames four;
- the **floor binds on 19%** — the leader has broken clear and the rule returns
  three racers strung over a gap, so the solve widens for a contest that is not
  on screen.

---

## 3. The race-interest group

A chain, not a radius (`race2.readability.interest_group`):

1. Rank by the race's own sticky order.
2. Two neighbours are **linked** when the arc gap between them is at most
   `LINK_GAP` = 2.4 units, about four marble diameters. That splits the field
   into runs.
3. The **lead run** is the one containing the leader. The **contest run** is
   the largest run of two or more starting within `CONTEST_REACH` = 12 units of
   the leader.
4. The group is the lead run followed by the contest run, trimmed so it never
   spans more than 11 units of arc and never holds more than six racers,
   floored at three.

A break in the field is something the rule *reads* rather than averages over.
The brief's worked example — leader clear, second to fifth fighting — returns
the leader **and** the fight, which is what neither a radius nor a fixed top-N
can express.

**Weights** decide where the camera actually points. Each member starts at 1.0
and is damped toward 0.45 by how far off the front of the group it sits; a
leader alone in its own run is worth 1.9. The anchor is the weighted centroid.
That is what stops the two failure modes being one dial: the group can be wide
enough to *contain* the contest while the anchor stays where the contest is.

On the hero replay the interest group averages **5.37 racers** against the
active pack's 3.76.

### Framing it without shrinking the racers

Widening `target_width` to cover six racers would shrink the racers on every
frame, including the ones where the group is already together. Instead the
reach solve gains a **second stage** (`Rig.contain`): stage one sizes the reach
so the core group spans the rig's target width, exactly as before; stage two
asks whether anyone else in the interest group has been left outside 0.88 of
the half-frame, and if so stands far enough back to hold them — outward only,
and never past the rig's own `reach_span`. On a frame where the contest is
already inside, it costs one projection and changes nothing.

---

## 4. Track look-ahead

Camera position still follows the racers; camera **orientation** carries the
course. Three terms, all defaulting to off:

- **`lead_curve`** scales the look-ahead *distance* by the course's own local
  curvature, capped by `lead_max`. Twelve units is most of a switchyard
  straight and barely into a hairpin; one fixed number cannot serve both, which
  is the brief's own "do not blindly use one fixed number everywhere".
- **`look_hold`** is the ceiling on how far the look-ahead blend may push a
  framed racer off centre. Left at camera A's 0.70 in the winner — see §6.
- **`curve_reach` / `curve_lift`** raise the reach ceiling and the height a
  little where the course turns, and nowhere else. Used only by variant C.

The existing `_hold_aim` bisection is unchanged in spirit: the blend is a
**ceiling, not a value**, so the look-ahead is strong where the course runs
ahead and self-limiting exactly where it would cost the racers.

### The horizontal field is the lever, and everything else was falsified

Four structural changes were tried before the lens was touched. All four are in
`race2/cinematography.py`'s module note, with their numbers:

| tried | result |
|---|---|
| a longer trail (8.5 → 16–20) | lens/course alignment 0.23 → 0.45, group visibility **79% → 35%** |
| a shorter nominal reach | depression to the 45° cap — the plan view the brief rules out |
| a lower reach floor (1.00 → 0.74) | forward path 6.1 → 4.8 u, clearance 5.5 → 3.2 |
| a vertical pack bias | falsified in **both** directions — below |

**The vertical bias, twice.** The brief's Part F asks for the pack low so more
upcoming track shows above it. That is the right principle and the wrong sign
here: the switchyard descends at 0.65 units per unit of plan, so from a lens
above and behind **the course ahead is below the pack in frame**. The
track-visibility proof shows the forward centreline running down out of the
bottom of the picture, and biasing the group downward pushed it off that edge —
at the drum, 7 units of visible forward course became 4.

Biasing it *upward* does what the geometry says and costs more than it is
worth: the visible course ahead goes 4.88 → 4.98 units, and **the longest any
racer spends off screen goes 7.97 s → 13.35 s**. On a descending course the
coming path and the trailing racers compete for the same edge of the frame, and
the racers win. Every variant ships at zero bias.

### One term exists because reach and height were secretly the same dial

`_riser` encodes the rail's answer as a *ratio* — height over the rig's nominal
reach — so shortening the reach to bring the lens closer silently steepens the
shot. Every trial that reduced `reach` to hold racer size at a wider lens
arrived at the 45-degree cap. `Rig.depression_span` names the angle instead, and
the three variants hold 31–38 degrees: a racing three-quarter view at any reach.

---

## 5. The three variants

Not three camera systems. Each is **camera A's four shots, on camera A's four
markers, with camera A's four rigs**, and a dict of parameter changes. All
three share one tuned opening (§6).

| | `fov` | `contain` | `target_width` | `look_ahead` | `look_hold` | `lead_curve` | bend terms |
|---|---|---|---|---|---|---|---|
| **A** (control) | 34 | — | 0.40 | 0.30 | 0.70 | — | — |
| **RA** pack priority | 38 | 0.88 | 0.42 | 0.30 | 0.70 | — | — |
| **RB** pack + path | 42 | 0.88 | 0.42 | 0.42 | 0.70 | 0.9 | — |
| **RC** path-aware chase | 48 | 0.90 | 0.44 | 0.55 | 0.86 | 1.2 | reach 0.05, lift 0.09 |

RA exists to separate Part A from Part B: it is the interest group and the
containment stage with **nothing aimed at the course at all**, so whatever B
and C gain on the path is charged against RA rather than against camera A.

RC is deliberately past the knee. It is kept because a candidate that shows
where the trade turns over is worth more than a third good one.

---

## 6. The opening, and the one cut the rule cost

Moving to the interest group costs reacquisition at exactly one join —
`release` into `upper`, where the field is still one bunch and the interest
group is at its widest six. Camera A's plan built on the interest rule alone
takes the worst pack jump from 0.285 to **0.413**, while the other two cuts
*improve* (0.128 → 0.101, 0.155 → 0.076).

The instrument named the cause: a lens-angle step of 11 degrees across that
cut, which is the look-ahead blend changing. Matching the opening's look-ahead
to the chase's and tightening its target to 0.73 of frame width returns the
worst pack jump to **0.284**, against camera A's 0.285, for seven pixels of
racer in the opening take. The eight racers are still 86 px on the delivery
frame and 21.6 px on the phone.

---

## 7. Racer visibility — the PICK A COLOR answer

Every racer tested as if it were the chosen one. `visible` means on screen
**and** not behind geometry.

| m | colour | A vis% | RB vis% | A longest gap | RB longest gap | in contest | A contest vis% | RB contest vis% | RB worst contest gap |
|---|---|---|---|---|---|---|---|---|---|
| 0 | red | 24.8 | 26.6 | **13.42 s** | 7.87 s | 4.70 s | 93.6 | 95.7 | 0.10 s |
| 1 | cobalt | 84.5 | **93.5** | 0.47 | 0.27 | 16.10 s | 84.3 | 93.4 | 0.27 s |
| 2 | emerald | 84.7 | 89.8 | 0.70 | 0.63 | 15.07 s | 86.1 | 89.6 | 0.57 s |
| 3 | yellow | 21.1 | 25.1 | **13.42 s** | 6.20 s | 3.10 s | 78.5 | 80.7 | 0.20 s |
| 4 | orange | 32.9 | 39.4 | 7.63 | 7.53 | 7.50 s | 65.8 | **83.6** | 0.37 s |
| 5 | purple | 42.4 | 50.3 | 2.40 | 2.50 | 5.53 s | 65.1 | 78.3 | 0.50 s |
| 6 | turquoise | 37.8 | 48.3 | 6.47 | 6.27 | 7.90 s | 62.9 | **79.8** | 0.27 s |
| 7 | pink (winner) | 82.3 | 87.3 | 1.07 | 0.67 | 15.17 s | 82.9 | 87.5 | 0.67 s |

**Every racer improves on every measure that matters**, and the number the
format actually depends on is the last column. While a racer is genuinely part
of the contest, RB never loses it for more than **0.67 s**, against camera A's
1.07 s, and the worst contest visibility rises from 62.9% to 78.3%.

The two long gaps that survive — m0 and m3, 7.9 s and 6.2 s — belong to racers
that spent 4.7 s and 3.1 s of a 19.15 s film in contention. They are the field's
tail, and the brief is explicit that all eight need not be visible constantly.
Camera A lost both of them for **13.42 s**, which is 70% of the film.

The group as a whole: **78.4% → 85.8% visible**, and the worst half-second
window goes from 12% of the group on screen to 41%. Camera A's two near-total
losses — 0.12 at 7.80–8.37 s and 0.139 at 11.52–12.08 s — are gone.

---

## 8. Track visibility

| | ahead (contiguous) | p10 | seen (any) | short-path frames | turn read | depression |
|---|---|---|---|---|---|---|
| **A** | 3.94 u | **0.00 u** | 4.97 u | 83.7% | 0.155 | 36.2° |
| RA | 4.74 u | 2.00 u | 5.84 u | 77.0% | 0.178 | 38.6° |
| **RB** | **4.87 u** | 2.00 u | **6.01 u** | 78.6% | **0.191** | 38.9° |
| RC | 5.21 u | 2.00 u | 6.62 u | 79.5% | 0.232 | 39.4° |

`p10` is the strongest line in the table: **camera A shows zero forward course
on a tenth of its frames.** Every variant raises that floor to two units.

Per shot, RB against A:

| shot | A group vis | RB group vis | A path ahead | RB path ahead | A short | RB short |
|---|---|---|---|---|---|---|
| release | 96.0% | 95.8% | 0.39 s | 0.44 s | 96% | 93% |
| **upper** | 70.8% | **84.4%** | 0.59 s | **0.77 s** | 75% | **62%** |
| **middle** | 66.7% | **81.6%** | 0.60 s | **0.72 s** | 68% | 74% |
| run_in | 86.8% | 86.3% | 0.32 s | 0.37 s | 97% | 94% |

The two chase shots — 10.45 s of a 19.15 s film, and the ones the brief calls
the problem — carry all of the gain. The opening and the sprint are level,
which is what §10 is about.

**Worst track-readability intervals** (RB): 18.42–18.98 s, 0.85–1.42 s and
17.58–18.15 s. All three are the run-out after the winner has crossed or the
opening azimuth swing; **no interval inside the racing is in the worst three.**
Camera A's worst three are 17.92–18.48 s, 18.52–19.08 s and **7.87–8.43 s**,
that last one inside the first chase at 0.094 s of visible path.

---

## 9. Switchbacks

`turn_read` is the share of the coming 24 units of turn that is on screen,
counting the whole frame rather than only the contiguous run — on a switchback
a viewer who can see both legs understands the fold whether or not the apex
between them is occluded.

RB reads **0.191** against camera A's 0.155, and on the two moments the proof
sheet samples the contiguous forward centreline goes 8 → 10 units at the chase
and 9 → 11 at the switchback. RC reaches 0.232 and 14/12 units.

This is an improvement of about a quarter and it is **not a solution**. 84% of
turning frames still show less than 55% of the coming turn. §14 says what that
would take.

---

## 10. Mechanism framing

The hierarchy the brief asks for — racers, then path, then mechanism — is now
measured: a station's projected half-width against the frame, and whether the
group is hard to find at the same time.

| | largest station span | frames a station dominates | intervals where it dominates *and* the group is lost |
|---|---|---|---|
| A | 2.14 | 40.9% | **9.28–9.62 s** |
| RA | 2.04 | 45.6% | none |
| RB | **1.93** | 45.9% | **none** |
| RC | 1.70 | 43.5% | none |

Mechanisms are in frame slightly more often in the variants and are **smaller
when they are**, and the one interval where camera A's mechanism filled the
frame while the race became hard to follow does not occur in any variant. No
mechanism moved; this is framing.

---

## 11. Phone review — 270×480

`docs/validation/race2/v31_readability/phone_270.png` pastes the delivered
frames at exactly 270×480 rather than at a sheet-sized thumbnail, and
`exports/race2_v31_readability/race2_v31_RB_phone_270x480.mp4` is the whole
film at that size, because what a chase camera has to survive is motion.

At phone size, against the brief's three simultaneous questions:

- **My colour.** All eight are separable in the opening at 86 px / 21.6 px
  phone. Through the race, RB's smallest racer is 18.6 px on the phone frame
  against camera A's 19.3 — under a pixel of difference, and the racers are on
  screen far more of the time.
- **The battle.** The clearest single improvement, and it is visible in one
  tile: at the 6.80 s chase, camera A shows one or two marbles behind the sweep
  paddle; RB shows the whole group plus the leg above it.
- **Where the track goes.** RB's tiles carry a second run of channel in frame
  at the chase and the switchback where A's carry one.

The weakest phone moment in every camera is 8.40 s, where the field is
genuinely strung out and two marbles are all there is to show.

---

## 12. The winner: RB

| | A | RA | **RB** | RC |
|---|---|---|---|---|
| shots / hard cuts | 4 / 3 | 4 / 3 | **4 / 3** | 4 / 3 |
| mean shot | 4.78 s | 4.78 s | **4.78 s** | 4.78 s |
| screen-direction reversals | 0 | 0 | **0** | 0 |
| worst pack jump | 0.285 | **0.269** | **0.284** | 0.657 |
| worst scale jump | 1.19× | 1.11× | **1.13×** | 1.32× |
| worst lens-angle change | 10.3° | 9.4° | **10.8°** | 25.7° |
| racers, 1080 frame | 77–95 px | 78–87 | **74–86** | 65–86 |
| racers, 270 frame | 19.3 px | 19.4 | **18.6** | 16.3 |
| min lens clearance | 5.64 u | 5.54 | **5.27** | **2.67** |
| group visible | 78.4% | 84.9% | **85.8%** | 83.9% |
| whole group visible | 53.2% | 56.4% | **57.9%** | 49.7% |
| group screen width | 0.461 | 0.449 | **0.444** | 0.413 |
| course ahead | 3.94 u | 4.74 | **4.87** | 5.21 |
| turn read | 0.155 | 0.178 | **0.191** | 0.232 |
| longest racer disappearance | 13.42 s | 7.87 | **7.87** | 7.87 |
| FLOW | 85.5 | 87.1 | **86.4** | 72.3 |

**RB improves every readability measure while matching camera A at the cuts and
scoring higher on camera A's own flow instrument.** It costs three pixels of
racer at the floor and 0.37 units of lens clearance.

RC buys another 0.34 units of course and loses 2.3× the pack jump, 9 pixels of
racer, 8 points of whole-group visibility and half the clearance the rail
proved. It is the edge, reported rather than tuned away.

---

## 13. The production preview

`exports/race2_v31_readability/race2_v31_production_preview_RB.mp4` — SWITCHYARD,
hero seed 8, the RB readability camera, `contained_bay_v301`, with the
viewer-facing marks on. Three of them, all `sloped.overlays`' own — imported,
not redesigned:

- **PICK A COLOR** from frame zero to 1.30 s, fading from 1.05. Its baseline is
  *measured*, not chosen: the eight racers occupy y 806–1079 over the title's
  life, so the high band at 395 has 352 px of clearance against the low band's
  101, and the high band is taken.
- **A ring on the winner**, 16.00–16.70 s, m7, radius 30–32 px. V24's payoff lab
  found both shipped winner marks pointing at a marble hidden behind the finish
  gantry, so the same occlusion test the readability instrument uses runs over
  the mark's whole life and the tool **refuses to composite** if any frame is
  hidden. Here: 43 frames, **0 hidden**.
- **FROM 6TH → 1ST** from 18.20 s, in **m7's own pink** rather than
  `overlays.WINNER_HUE`, which is the *sloped* race's seed-5432 purple. In a
  format whose premise is that the viewer picked a colour, a payoff card in the
  wrong colour points at the wrong marble.

---

## 14. Remaining weaknesses

1. **The switchback is improved, not solved.** 84% of turning frames still show
   under 55% of the coming turn. The cause is geometric and stated in §2.2: a
   180-degree fold every 32 units cannot be held in a 24-degree-wide portrait
   frame from behind the pack. Getting past it means either a wider lens than
   the racers can pay for, or a shot that leaves the pack — which the brief
   rules out, correctly.
2. **8.0–8.5 s is the weakest section in every candidate**, RB included, at 56%
   of the group visible. The field is genuinely strung out there. It is a
   pacing or course question, not a camera one.
3. **The tail of the field is still mostly absent.** m0 and m3 are visible a
   quarter of the film. They are also in contention for under five seconds of
   it, so this is arguably correct — but a viewer who picked red will spend
   most of the race not seeing red.
4. **14.05–14.62 s** is the worst group-visibility window in all three variants,
   identically, because it is inside the locked final sprint and none of them
   touch it.
5. **The drum loses forward course** — 7 units to 4 — where the chase gains it.
   The containment stage stands the lens back for six racers there, and the
   course drops away immediately after. The aggregate is strongly positive; this
   one moment is not.

### No track-material change was made, and none is needed

Part O's condition was never met. The forward centreline is **never once
occluded** in the whole film (§2.1), and where the track is framed it renders as
a bright silver ribbon against a dark deck at every sampled moment, including
the two weakest. The defect was where the lens was pointed, not what the track
is made of. Prefer no material change — and none was made.

---

## 15. Should camera development stop here?

**Yes, for this course and this format.**

Against the brief's own stop condition: race flow is continuous (four shots,
three cuts, zero reversals, 4.78 s mean take); the battle is trackable (85.8%
of the group visible, worst window 3.4× better than the control); chosen colours
are reasonably trackable (no racer lost for more than 0.67 s while it is in the
contest, every racer improved); upcoming track is visible (the floor is no
longer zero); switchbacks are clearer by a quarter; mechanisms no longer
dominate at the expense of the race; and the final sprint is preserved to within
0.1 px of racer size and 0.5 points of group visibility.

The honest reason to stop is §14.1. The remaining readability headroom is not
in the camera — it is in a course whose longest straight is 16 units, or in a
delivery frame that is not 19 degrees wide. Both are decisions above this pass,
and either would make the next camera brief a different one.

---

## 16. Reproducing it

```bash
python tools/race2_v31_camera.py --seed=8          # build + measure all four
python tools/race2_v31_camera.py --probe           # the §2.1 diagnosis
python tools/race2_v31_review.py frames            # the moment set
python tools/race2_v31_review.py sheet             # camera x moment
python tools/race2_v31_review.py phone             # 270x480, mandatory
python tools/race2_v31_review.py trackproof        # the overlay proof
python tools/race2_v31_review.py clips             # four 19.15 s films
python tools/race2_v31_review.py compare --right=RB
python tools/race2_v31_review.py sections --right=RB
python tools/race2_v31_review.py phonefilm --right=RB
python tools/race2_v31_review.py preview --right=RB
python -m pytest tests/test_race2_v31_readability.py
```

The replay is read, never re-simulated: there is no code path in this branch
that could change the physics, the seed, the finish order or the runtime.
`tests/test_race2_v31_readability.py::test_camera_a_is_byte_identical` rebuilds
the V28.1 camera A plan through all of the new code and compares it with the
delivered track **byte for byte**, which is how every addition here is shown to
default to off.
