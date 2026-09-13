# V22 — an elevated chase camera

A prototype of a new primary camera language for the sloped race: a lens that
rides the course behind and above the pack for the whole race, instead of a
sequence of fixed stands that the field runs through.

Seed 5432, replay digest
`aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6` — the same
race V1.15 locked and V21 delivered. **No physics, no seed, no course geometry,
no route balance, no start mechanism and no finishing order is touched by
anything in this branch.** The replay is read, never written; the chase is
solved from it and nothing downstream re-simulates.

    python tools/sloped_integrate.py --seed 5432 --stage race --routes both
    python tools/sloped_chase_camera.py --seed 5432 --stage all

Everything new lives in two files, `sloped/chase_camera.py` and
`tools/sloped_chase_camera.py`, plus `tests/test_sloped_chase.py`. No
production module is edited — `git status` on this branch shows additions only
and no modifications — and the chase emits the **same track document**
`sloped.cameras` writes, so `sloped_race_scene.gd` renders it unchanged.

---

## 1. The complaint

V21 made every shot readable one shot at a time. Watched end to end the film
still reads as *fast*, and the reason is the grammar rather than the physics.
`sloped.cameras` places a blocking camera per section: a lens stands at a
bearing off the course, the field runs through its frame, and the edit cuts to
the next stand. Measured on this seed's V21 track:

* the lens teleports **39.7, 33.7, 44.5, 49.3 and 31.7 layout units** at five of
  its ten boundaries;
* at three of them the pack's screen direction turns through eighty degrees or
  more (cos −0.16, −0.15, −0.28);
* and the course ahead of the leader is in frame for **0 to 4.8 layout units**
  in every race shot.

That last one is the whole complaint in one number. A viewer is never shown
where the race is going before it gets there, so every shot is a surprise and
every cut is a reacquisition.

---

## 2. What a chase camera is here

Three points on the racing line and nothing else:

    pack      =  course at (pack progress)
    position  =  pack − forward · trail  +  rise
    aim       =  course at (pack progress + look)

`forward` is the course's own tangent at the pack. There is no bearing, no
extent and no side, which removes three whole classes of defect that
`sloped.cameras` carries machinery for: `Cut.side`'s mid-shot terrain flip,
`Cut.fixed_heading`'s 180-degree tangent reversal at the junction, and the
"camera looking across a leg has the channel's guard in front of the cradle"
rule — a chase looks *along* the channel for its whole length, which
`sloped.cameras` itself identifies as the only bearing from which a marble is
open to the lens.

### The three forms that do not work

Written honestly, because each cost a solve and each is a fact about this
course rather than about this module.

**1. The camera may not stand on the racing line.** The obvious form puts the
lens at `course at (pack − trail)`, which keeps it over the course and
therefore never inside the mountain. This is a switchback: legs 1, 2 and 3 run
back and forth across one hillside, so two points 44 layout units apart *along
the arc* can be twenty apart across it with a hairpin between, and the chord
joining them — which is the view axis — cuts the corner. Measured at replay
11.92 s the pack sat at leg2 sample 69, `pack − trail` at leg2 sample 27 and
`pack + look` at leg3 sample 25; the eight racers projected to x = 1500–1700 of
a 1080-wide frame and the shot held **0.6 racers of 8**. Arc length is the right
measure for *who* to follow and the wrong one for *where to stand*.

**2. The aim may not be a chord.** Interpolating the aim between the pack and a
point downstream puts it **under the mountain**. A chord of a concave-upward
curve lies below the curve; the first descent leaves the launch steeply and
flattens into leg 1, and the racing line hugs a bench cut 2.8 units deep. At
replay 8.883 s the aim sat at y 25.81 against a ground height of 28.14, and the
lift loop ran to its 26-unit ceiling trying to see over a hill that was not the
obstruction — producing a 52-degree plan view for a fault that had nothing to
do with where the camera stood. The aim is a point *on* the course.

**3. The look-ahead is an angle budget, not a distance.** On a course that
doubles back, "fifteen units ahead" is around the corner and pointing the other
way. So `look` is a maximum, and the solve walks it down until the aim is
within `MAX_LOOK_YAW` = 6 degrees of yaw of the direction to the pack. Six is
read off the delivery frame: Godot keeps the vertical angle, so at fov 36 on
1080×1920 the horizontal half-angle is 10.36 degrees — the *narrow* axis of a
portrait frame — and the remaining four degrees are the pack's own width. On a
straight the budget is never spent; into a hairpin it pulls the look-ahead to
nothing, which is the camera declining to look round a corner when looking
round the corner would mean looking away from the race.

---

## 3. Pack targeting

Five rules, measured over the chase phases of the same solve:

| rule | px median | px tail | coverage | lost s | racers in frame | worst phase |
|---|---|---|---|---|---|---|
| centroid | 52.4 | 42.1 | 0.833 | 1.10 | 6.66 | routes 0.68 |
| median | 52.2 | 42.0 | 0.851 | 1.13 | 6.81 | routes 0.72 |
| trimmed | 52.0 | 41.6 | 0.856 | 1.10 | 6.85 | routes 0.73 |
| **leader** | **59.2** | **50.3** | **0.545** | **3.48** | **4.36** | **fork 0.26** |
| adaptive | 52.1 | 41.6 | 0.862 | 1.10 | 6.89 | routes 0.75 |

The finding is blunt: **which centre you pick barely matters, and picking the
leader instead of a centre matters enormously.** The four centre rules lie
within 3% of each other on every column; the leader loses a third of the field
and spends three and a half seconds with most of it off screen. `adaptive`
ships — median blended toward the front by up to 45% of the gap when the field
is tight, and the plain median once it spreads — on a margin over `trimmed` of
0.04 racers, which is not a mandate for it so much as a coin toss between four
acceptable answers.

The centre is taken **per route and then averaged by member count**, because
after the fork the two lobes have different arc parameterisations (blue 13.8 +
59.5 sim units of lead and run, orange 21.9 + 49.4), so one scalar progress
means two different places. The route weights are smoothed over about a third
of a second *before* they are used: member counts are integers, the lobes are
31 layout units apart, and one marble changing sides steps an unsmoothed camera
about four units in a single frame.

---

## 4. The phases

Five, each a set of numbers the solve ramps to rather than a place the camera
stands. Every distance is in layout units.

| phase | until | trail | rise | look | spread | ramp |
|---|---|---|---|---|---|---|
| descent | leg2_start | 26 | 13 | 16 | 0.6 | 0.5 |
| obstacle | sweep | 19 | 11 | 15 | 1.8 | 1.1 |
| fork | branch_in | 28 | 20 | 14 | 0.2 | 1.2 |
| branches | branch_out | 34 | 26 | 18 | 0.4 | 1.3 |
| merge | — | 26 | 34 | 16 | 0.45 | 1.2 |

### The trail breathes with the field

A constant trail frames a constant amount of course, and this field is not a
constant size: it spans 3.5 layout units in the spinner corridor and 31 across
the two branch lobes. So the trail is the phase's own plus `spread` units for
every unit the subject set is spread beyond nine, with the rise scaled to match
so that opening up is the same shot from further away rather than a flatter one.

Swept at the branches with a fixed trail, the trade is a straight line and
**nothing on it reaches the 48 px floor**:

| trail | px median | coverage | racers visible | both routes |
|---|---|---|---|---|
| 24 | 41.3 | 0.623 | 4.44 | 0.78 |
| 32 | 35.9 | 0.707 | 5.06 | 0.83 |
| 40 | 31.5 | 0.776 | 5.44 | 0.83 |
| 46 | 28.6 | 0.792 | 5.61 | 0.83 |

Two lobes 31 units apart do not fit a phone frame at a readable size, and no
camera position changes that. This is the brief's "do not attempt to keep every
marble huge if they are physically far apart", as a measurement.

### The set-points are not fitted to one seed

`branches.spread` was 0.0 after tuning on 5432 alone, which is the value that
maximises scale on this race. Checked against two fresh seeds it collapsed:

| branches.spread | 5432 cov | 5558 cov | 5585 cov | mean px |
|---|---|---|---|---|
| 0.0 | 0.860 | 0.441 | 0.391 | 37.7 |
| 0.4 | 0.879 | 0.559 | 0.473 | 35.2 |
| 0.8 | 0.904 | 0.627 | 0.527 | 32.8 |
| 1.6 | 0.973 | 0.691 | 0.563 | 28.9 |

0.4 ships. For scale, V21 on the same three seeds holds **0.356, 0.347 and
0.195** coverage at its `branch` shot, so every value in that table is a large
improvement on the baseline and the choice inside it is a scale-versus-coverage
preference rather than a pass/fail.

---

## 5. V22 against V21, same replay, same instants

`px` is the median racer's diameter in the 1080×1920 delivery frame; `vis` is
racers actually on screen after `sloped.sightlines` walks the drawn course as
solid geometry; `hid` is the share of in-frame racers the course hides;
`ahead_u` is how many layout units of upcoming racing line a viewer can see
past the leader.

**V22 — 8 cuts, 3 of them an actual jump, 20.00 s**

| phase | px | cover | vis | hid | both | turn/f | ahead_u |
|---|---|---|---|---|---|---|---|
| start * | 70.3 | 0.852 | 4.70 | 0.31 | 0.85 | 0.08 | 41.2 |
| descent | 48.0 | 0.947 | 6.76 | 0.11 | 1.00 | 0.51 | 17.2 |
| obstacle | 69.2 | 0.912 | 6.40 | 0.12 | 1.00 | 0.56 | 36.4 |
| fork | 47.8 | 1.000 | 7.53 | 0.06 | 1.00 | 0.14 | 21.1 |
| branches | 34.0 | 0.879 | 7.00 | 0.02 | 1.00 | 0.50 | 34.5 |
| merge | 28.4 | 0.766 | 4.94 | 0.19 | 0.67 | 0.42 | 11.5 |
| finish * | 60.4 | 0.265 | 1.14 | 0.15 | 0.34 | 0.01 | 13.4 |

**V21 — 11 cuts, 10 of them a jump, 19.15 s**

| cut | px | cover | vis | hid | both | turn/f | ahead_u |
|---|---|---|---|---|---|---|---|
| start | 76.0 | 0.795 | 4.67 | 0.27 | 0.85 | 0.08 | 0.0 |
| descent | 69.7 | 0.925 | 7.30 | 0.01 | 1.00 | 0.09 | 1.9 |
| long | 56.0 | 0.773 | 6.17 | 0.00 | 1.00 | 0.00 | 2.9 |
| hairpin | 58.5 | 0.818 | 5.73 | 0.12 | 1.00 | 0.10 | 0.0 |
| straight | 71.2 | 0.777 | 6.15 | 0.02 | 1.00 | 0.00 | 3.8 |
| obstacle | 135.0 | 1.000 | 7.65 | 0.04 | 1.00 | 0.05 | 1.9 |
| split | 35.9 | 0.925 | 6.75 | 0.09 | 1.00 | 0.07 | 4.8 |
| branch | 49.5 | 0.356 | 2.57 | 0.10 | 1.00 | 0.00 | 9.6 |
| merge | 39.8 | 0.585 | 2.75 | 0.42 | 0.75 | 0.00 | 15.3 |
| finish | 60.4 | 0.265 | 1.14 | 0.15 | 0.34 | 0.01 | 13.4 |

`*` marks a V21 lens carried over.

### What moved

* **Camera cuts: 10 → 3.** Two of the three remaining are the handovers into
  and out of the V21 bookends; the third is V21's own omission inside the start.
  Between `descent` and `merge` — twelve and a half seconds of racing — the lens
  travels **0.000 layout units** across each of the four phase boundaries,
  because they are adjacent samples of one solve rather than cuts.
* **Course ahead: 0–4.8 units → 11.5–36.4 units.** The largest single change and
  the one the brief leads with. V21's blocking shots essentially never show the
  upcoming course; the chase always does.
* **The fork:** 35.9 px → 47.8 px, 6.75 → 7.53 visible racers, coverage 0.925 →
  1.000, both routes in every sampled frame.
* **The branches:** 2.57 → 7.00 visible racers, coverage 0.356 → 0.879. This is
  the shot V21 documented as its worst residual, and it is 2.7× better.
* **The merge:** 2.75 → 4.94 visible racers, occlusion 0.42 → 0.19. V21's own
  note says the catch basin "hides 42% of what is in frame at any elevation
  under the file's own 46-degree ceiling"; looking along the channels from
  behind rather than across them halves that.
* **The start is level, not better.** 4.70 visible against 4.85 at this
  sampling stride, 4.81 against 4.76 at a finer one. What the re-bearing buys
  is the handover into the chase, not visibility — see §7.
* **Racer scale is the price.** V21 is bigger through the first half — 69.7,
  56.0, 58.5, 71.2 and a spectacular 135 at the obstacle against the chase's
  48.0 and 69.2 — and bigger at the merge, 39.8 against 28.4.

---

## 6. Section behaviour

**A. First descent.** `descent`, 7.62–9.67 s. 48.0 px, 7.6 of 8 in frame and
6.76 visible, 17.2 units of course ahead, no second below three-quarters
coverage. The hairpin at the end of leg 1 is taken with the tangent slew
engaged: the camera lags into the apex and catches up out of it.

**B. Curves.** The course tangent reverses through most of 180 degrees in the
twenty frames a field takes to round an apex, and the camera hangs off that
tangent at a 26-unit radius — 3.0 degrees a frame of yaw is 1.4 layout units a
frame of lens, which `cameras.check_track` calls a cut in the middle of a shot.
Smoothing cannot fix it: a symmetric mean spreads the turn and leaves its
integral, and at 54 passes the descent still whipped at 3.00 degrees a frame.
`MAX_YAW_RATE` = 0.75 degrees a frame changes the answer rather than the
schedule.

**C. Obstacle.** `obstacle`, 9.67–15.10 s, one continuous phase over approach,
interaction and exit. 36.4 units of corridor are visible ahead of the leader, so
the spinners are in frame long before the field reaches them; the trail closes
as the corridor bunches the field, and the median racer is 69.2 px.

**D. Fork.** The strongest result, and it needed no special case. Upstream of
the divider both routes share every run, so `pack − trail` is the same point on
both and the camera is *behind the decision* by construction; downstream
`pack + look` has already split, so the route-weighted aim is the midpoint of
two diverging mouths — the divider — because that is where the expression
lands, not because a node was typed in. `fork.rise` is 20 against the descent's
13 and `fork.trail` 28 against 19, which is the brief's "rises and widens", and
the result is 8.0 of 8 in frame, 7.53 visible, both routes in every sampled
frame, at 47.8 px.

**E. Branches.** `branches` rises to 26 and trails 34, and the spread response
opens it further as the lobes separate. 7.00 visible racers against V21's 2.57,
at 34.0 px. The scale is under the floor and deliberately so: see §4.

**F. Merge.** `merge` rises to 34 — the highest set-point in the table — because
the `MergeCatch` basin's rim stands above a marble's centre and a lens that is
not looking down into it is looking at its wall. Both streams are in frame and
unobstructed in 67% of sampled frames against V21's 75%, with 4.94 visible
racers against 2.75.

**G. Final.** Handed to V19's finish lens at 20.20 s, unchanged. The brief says
not to replace it without measured evidence of an improvement and there is none.

---

## 7. The start bearing, and a mistake worth recording

V21 photographs the trapdoor from a bearing of 28 degrees — from downstream,
looking back up at the field as it drops. A chase looks the other way down the
same course, so joined, the two reverse the pack's screen direction at cosine
**−1.00**.

Swept on the frustum count, 200 degrees looked like the fix: eight racers of
eight in frame against 28's 6.4, coverage 1.000 against 0.795. Swept again
through `readability.visibility_report`, 200 puts **three** of those eight on
screen and hides five behind the machine's own housing.

V21's own findings say this in as many words — *a frustum count is not
visibility* — and this module repeated the mistake on its first pass. The
render was stopped and re-cut.

Over the release window, every other frame (58 samples):

| bearing | px | coverage | in frame | visible | hidden | handover |
|---|---|---|---|---|---|---|
| 28 (V21) | 76.0 | 0.795 | 6.4 | 4.76 | 0.256 | −1.00 |
| 180 | 71.1 | 1.000 | 8.0 | 3.98 | 0.502 | −0.16 |
| 200 | 71.0 | 1.000 | 8.0 | 2.91 | 0.636 | −0.07 |
| **230** | **70.3** | **0.852** | **6.8** | **4.81** | **0.299** | **+0.81** |

**230 is level with V21 on racers actually on screen, not better.** 4.81 against
4.76 is inside the sampling noise — measured every sixth frame instead of every
second the two swap places, 4.70 against 4.85 — and the claim here is only that
the swing does not *cost* visibility while it removes the reversal. It costs six
pixels of median scale and 0.04 of hidden share; it buys a handover of +0.81
against −1.00. 200, which the frustum count preferred, would have cost 1.9
racers of the 4.8 that were on screen.

Both start windows swing, so the opening and the release agree across V21's
omission. The opening is level too: 7.50 visible against 7.45.

---

## 8. Weaknesses, and what an integration session should know

1. **Racer scale in the second half is below the readability floor.** `branches`
   at 34.0 px and `merge` at 28.4 px against `MIN_MEDIAN_PX` = 48. The floor is
   unreachable there for any camera — V21 reaches 49.5 px at the branch only by
   holding 2.6 racers of 8 — but a reviewer should decide which failure they
   prefer before this ships. The dial is `spread` and `trail` per phase and the
   trade curve is in §4.

2. **The obstacle phase loses the field for 0.78 s.** The approach along leg 2
   is where the field is most strung out; `obstacle.spread` of 1.8 already pulls
   the camera back and does not fully close it.

3. **The merge → finish handover still jumps.** The pack moves 0.44 of the frame
   diagonal, against V21's 0.60 at the same join. It is better and it is not
   fixed, and it cannot be fixed without re-lensing the finish.

4. **A continuous chase cannot omit time.** V21's edit drops 0.85 s between the
   obstacle and the fork; a chase that runs through that span has to show it, so
   the proof is 20.00 s against V21's 19.15 s. Any Short cut from this will need
   its pacing re-decided — which is explicitly not this branch's work.

5. **`turn/f` is an order of magnitude above V21's** — 0.42 to 0.56 degrees a
   frame against 0.00 to 0.10 — because the camera is always moving. That is the
   design, not a defect, but it is the number most likely to read badly to
   someone who prefers locked-off shots, and it is the one thing here that a
   still cannot show.

6. **The set-points are tuned on one seed and sanity-checked on two.** §4 shows
   the chase beating V21 comfortably on all three at the fork and branches, but
   5558 and 5585 both sit below 0.75 coverage at `branches` and `merge`. A
   production adoption should sweep more seeds.

7. **The frames carry more empty hillside than V21's do.** No metric here sees
   this and the contact sheet makes it obvious: a lens behind the pack looking
   down a ribbon of course fills the corners of a portrait frame with unlit
   mountain, where V21's tighter stands fill them with the machine. It reads as
   more air and less subject even where the racer count is better. If this
   language is adopted, the next pass is a composition one - the dials are
   `look` (how much of the frame the course ahead occupies) and `fov`.

8. **Integration surface.** `build_chase` returns exactly the document
   `cameras.build_track` returns, with `chase: true` on the phases it solves
   and V21's cuts passed through untouched. Nothing in `sloped/cameras.py`,
   `sloped/presentation.py`, `tools/sloped_short.py` or `tools/sloped_short_qc.py`
   is edited or needs to be. `check_chase` runs the production checker and
   retires exactly one of its findings — `MAX_AIM_DRIFT`, which assumes an aim
   that sits on the field — replacing it with a budget the look-ahead sets; the
   retirement applies to chase cuts only and is pinned by two tests.

---

## 9. Proof

    output/sloped_race_v1/chase_v22_5432.mp4          the chase, 20.00 s
    output/sloped_race_v1/chase/chase_5432.json       the camera track
    output/sloped_race_v1/chase/metrics_5432.json     every number above
    docs/validation/sloped_race_v1/v22_chase/sheet.png    V21 over V22, nine moments
    docs/validation/sloped_race_v1/v22_chase/phone.png    the same at 270x480
    docs/validation/sloped_race_v1/v22_chase/stills/      the eighteen frames

The nine moments are requested by **replay** second and converted through each
track's own edit map, so every pair is the same instant of the same race seen
through two camera languages.
