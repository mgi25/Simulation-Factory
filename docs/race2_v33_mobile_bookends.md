# Race #2, V33 — mobile-first bookends over a frozen middle

**Branch** `v33-mobile-race-bookends`, from `main` at
`157c818d4bbda65bf98ddc699b6dd8f9348295f4` — the commit that shipped Test #3.

    python tools/race2_v33_bookends.py all

Eight files, and the scope is a test rather than a promise
(`test_the_branch_adds_bookends_and_touches_nothing_else`):

```
race2/bookends.py                                     the two stands, parametric
race2/opening.py                                      the hook cameras and the handoff
godot/assets/marble_machine/course/race2_bookends.gd  the builder
godot/scripts/race2_scene.gd                          one seam, off by default
tools/race2_render.py                                 one flag, absent by default
tools/race2_v33_bookends.py                           the lab
tests/test_race2_v33_bookends.py                      26 tests
docs/race2_v33_mobile_bookends.md                     this
```

plus `docs/validation/race2/v33_bookends/`, which is measurement output. No
physics, no replay, no seed, no course, no mechanism, no environment, no light,
no material, no track profile, no payoff and no audio is touched.

---

## 1. Why this pass exists

The analytics, not a judgement about the film:

| | Test #2 | Test #3 (Race #2, V32.2) |
|---|---|---|
| stayed to watch | **41.7%** | 33.2% |
| average view duration | 13 s of 21 s | 14 s of 20 s |
| share of the film viewed | 62% | **70%** |

Two numbers moved in opposite directions. The share of the film a viewer who
stays gets through went **up** by eight points — the middle of Race #2 is
better than Test #2's. The share who stay at all went **down** by 8.5 points —
the opening is worse.

So the correct experiment is not a new race. It is Test #2's opening clarity
with Test #3's middle, and everything else held still.

## 2. The controlled-test principle, as a constraint on the code

The variable under test is **bookend clarity**. Everything else is held by
construction rather than by care, and each of the four mechanisms is a
different kind of lock:

1. **The simulation is not reachable.** `race2/bookends.py` imports no physics
   and defines no `MarbleModule`; nothing in `race2` imports it. Both
   directions are asserted by parsing the import tables
   (`test_nothing_in_this_branch_reaches_the_simulation`), because a substring
   search finds the module docstring's own promise not to.
2. **The camera rewrite is one cut of four.** `opening.rewrite_track` copies
   `upper`, `middle` and `run_in` through as *the same objects*, and the lab
   refuses to write a track whose later cuts do not serialise identically to
   the source's.
3. **The renderer's seam is off by default.** `race2_scene.gd` returns
   immediately with no `--bookends=`, and `tools/race2_render.py` appends the
   flag only when it is given. §14 is the experiment that proves this rather
   than asserting it.
4. **The soundtrack is a stream copy.** Not rebuilt, not re-normalised, not
   re-encoded: `ffmpeg -c:a copy` from the delivered V32.2 Short. Part I says
   the audio is closed and this is the strongest available way of saying so —
   the same trick, in the other direction, that V32.2 used to lock its picture.

## 3. What Test #3's opening actually does

Two instruments, and the difference between them is the finding.

**Projected**, by putting the eight resting centres through the shipped camera,
a racer is 78.3 px across at 1080 and 19.6 px at 270.

**Measured on the delivered frame**, by rendering the opening as a per-racer
matte and counting pixels, the median racer is **59.11 px**. The ratio of the
two areas is 0.57: **43% of every racer is behind the start module's own
structure**, which is what the picture shows — eight domes above a black comb,
not eight balls.

The rest of frame 0:

| | Test #3 frame 0 |
|---|---|
| median visible racer diameter @1080 | **59.1 px** |
| the same at 270 × 480 | **14.8 px** |
| racer area, share of frame | **1.06%** |
| nearest two centres | 1.86 diameters |
| the racers, in y | 906 → 983 px, a **77-pixel band** |
| the leftmost racer's edge, in x | **−9 px** — clipped by the frame |

And one more, which no report in the chain has carried before. Counting racers
visible per frame over the opening two seconds:

```
Test #3   8 8 2 0 0 2 8 7 8 8 7 7 7 7 7 7 7 7 8 8 8      (every sixth frame)
```

**Between about 0.2 s and 0.5 s there is no racer on screen at all** — 15
frames of the first two seconds have none. The shipped hook shows eight
colours, asks the viewer to pick one, and then removes all of them for a
quarter of a second at exactly the moment the race starts. Over the first two
seconds the mean is 6.18 of 8.

It is not a framing failure. Projected, all eight racers are inside the frame
on **every one of those frames**; they are *occluded* — the field falls through
the floor it is standing on, behind the start module's own comb, and there is
nothing there to see past. §8 has both instruments side by side.

The same diagnosis at the other end: the sprint's last shot has **no finish
structure in it**. §10 is what was found there, and it is worse than missing
architecture.

## 4. The start stand

`race2.bookends.StartStand`, authored in the start site's own
`(along, up, across)` frame, where `along` is the direction the race runs and
`up` is world +Y. Every dimension is a field and nothing is hard-coded to eight
racers: `test_the_stand_is_built_from_the_course_and_not_from_a_constant`
builds a six-bay stand at a different pitch with no other edit.

What it puts on screen, in the order the §3 diagnosis lists the failures:

| part | what it answers |
|---|---|
| two **towers** outboard of the release panel, and a **skirt** behind it | the stand has mass and a footing, so it is a stand |
| eight **bay backing panels**, one behind each racer | each racer is read against its own pale panel rather than against the room |
| nine **fins**, one either side of every bay | the row is eight *positions*, not eight dots |
| a **back board** with a pearl cap and one lit line | the void behind the racers is gone |
| a **portal** — two posts and a header, behind the board | a top edge against the room, and something to read as machine |
| a **gate rail** at the front of the deck, with two guides | closed → open, and a reason the racers are waiting |

Thirty-nine parts, of which three move. There is deliberately nothing in front
of the bays and nothing under them — §4.1 — so the route out of the stand is
the first thing in the frame after the racers themselves.

### 4.1 There is no plinth under the bays, and that is the trapdoor

The obvious way to give a start stand mass is a block beneath it. The first
build had one and `clearance` measured it at **0.000** from a racer centre.

Race #2's start is a *trapdoor*: the field falls 1.4 units through the floor it
is standing on and then rolls forward underneath the stand. The volume directly
below and directly in front of the bays **is the racing line**. So the mass is
in two side towers outboard of the panel and one skirt behind it, and the
middle and the front are deliberately open — which is also the brief's "obvious
downward / forward route into the race". The constraint and the composition
wanted the same shape.

### 4.2 The bay backing is behind the racers, not under them

A light floor plate under each racer is the obvious way to separate a ball from
a dark deck. `clearance` measured every one of the eight at **0.002** from a
racer centre, for the same reason: a static plate at deck level is a plate the
field falls through.

A panel at the *back* of the bay is never in the fall line, and it is better
for the picture anyway — it is behind the ball in the lens rather than under
it, so it separates the silhouette instead of the contact shadow.

### 4.3 The back board shadows the bays, and the fix is a flag

`contained_bay_v301`'s key light is at rotation `(-46, -58, 0)`, which travels
`(0.589, -0.719, -0.368)`: it arrives from **upstream**, 46° above the deck —
and the back board stands directly in its path. A board 1.74 tall throws its
shadow 1.14 downstream of its own face, landing at `along` −0.48. The racers
sit at −0.65, **inside it**.

The first render of the stand has eight racers in shade in a shot whose entire
job is their colour.

Lowering the board to 0.89 would clear the shadow and would also stop it being
a backdrop. So the board, its cap, the portal and the bay panels are marked
`shadow: false` — they receive light and do not cast it, which is what a
backdrop panel does in any lighting set-up. No light moved, no other surface
changed, and the racers got back the key they had before the stand existed.

**The general lesson:** a structure added *behind* a subject is a structure
added between the subject and the key. Check the profile's light rotation
before, not after.

## 5. The gate

It **retracts downward** and its top edge is level with the deck.

Three forms were measured against the three hook compositions:

| form | result |
|---|---|
| a rail above the bay mouths, 0.78–1.02 | the ray from a 22° lens to a racer centre crosses the gate plane at 0.94: **all eight blocked** |
| a rail that *lifts* through that plane on release | sweeps across the racers during the half second a viewer is choosing a colour |
| **a rail at the front of the deck, topped at 0.02, dropping into the plinth** | clears every racer in every composition by 22–69 px, and cannot cross one at any elevation |

The third is the brief's own "retracting front rail", and the reason it is
right is not taste: the *sight cone*, not the image, is what decides, and a bar
whose top is below the lowest racer's lowest point is below every sight line
there is. `test_the_gate_never_covers_a_racer` asserts that geometrically, so
no future composition can reintroduce the defect.

**Timing is the physics'.** `DropStart` releases at 0.10 s over 0.16 s and the
gate's motion group carries exactly those two numbers, read off
`panel_release_times()`. The build refuses if the eight panels do not release
in one tick — one gate is only honest while the floor is.

The curve is a smoothstep over the release window, is monotone, and is a pure
function of seconds, so a still taken at *t* matches the clip's frame at *t*.
`test_the_gate_animation_is_deterministic_and_bounded` checks all three.

## 6. The three hook compositions

Solved, not authored. `opening.solve` walks the camera in until the projected
row will not fit the frame any tighter; `opening.measure` reports what that
bought.

### 6.1 The cap, and the only lever past it

Eight racers at a 0.82 pitch are 10.07 diameters centre to centre, 11.07
including the two end balls. A row that exactly fills a 1080-wide frame
therefore caps a racer at **97.6 px**, whatever the shot is dressed with. Test
#3 gets 78.3, which is 80% of that cap: its opening is not far off the best a
dead-front row can do.

The lever is **obliquity**. Viewed at an azimuth θ off the course axis the
row's apparent width falls as cos θ while a racer's diameter does not, so the
camera can come closer. It costs depth spread and, eventually, separation:

| azimuth | distance | racer @1080 | nearest centres | racer area |
|---|---|---|---|---|
| 0° | 22.6 | 83.9 px | 1.44 d | 2.13% |
| 44° | 19.7 | 96.0 px | 0.91 d | 2.83% |
| 65° | 14.5 | 130.5 px | 0.53 d | 5.36% |
| 90° | 6.8 | 281.1 px | **0.19 d** | 30.3% |

At 90° the racers are enormous and the row is a pile. The second lever is the
**lens**: a long lens at a greater distance compresses the near-far ratio, so
the same obliquity costs less separation, and a raised camera slants the row
across the portrait frame, which is 1.78× as long as it is wide.

### 6.2 The three

All three are solved to the same fit (0.92 of frame), which is what makes the
comparison an experiment.

| | A — front three-quarter grid | B — low three-quarter, along the row | C — elevated three-quarter |
|---|---|---|---|
| azimuth / elevation / lens | 44° / 22° / 20° | 78° / 14° / 26° | 58° / 42° / 18° |
| solved distance | 29.34 | 12.89 | 28.01 |
| racer @1080 | 105.2 px | **183.0 px** | 123.0 px |
| racer @270 | 26.3 px | 45.7 px | **30.8 px** |
| nearest centres | 1.00 d | **0.35 d** | 1.01 d |
| near/far ratio | 1.13 | 1.53 | 1.14 |
| racer area | 3.37% | 10.73% | 4.61% |
| blocked by the stand | none | none | none |
| frames holding all eight | **111 of 133** | 94 | 105 |
| frames holding none | 0 | 0 | 0 |
| handoff step ratio | 1.000 | 1.000 | 1.000 |

### 6.3 A true rear hook is not available, and the number is 52

The brief asks for a *low rear* three-quarter as composition B. A camera
upstream of the bay row looks straight through the back board, which rises 1.74
above a deck the racers sit 0.35 above. Clearing its top edge on the way to a
racer needs an elevation of about **52°** — the map-like view the same brief
rules out. Measured directly, a camera at azimuth 118° and elevation 11° has
the board between it and **six of the eight** racers.

The two wants — a board that fills the void behind the racers, and a lens
behind them — are mutually exclusive on this stand, and the board is worth
more. B was taken round to 78°, the lowest raking angle at which nothing on the
stand is between the lens and a racer.

## 7. The chosen hook

**C, the elevated three-quarter.** It is not the biggest racer in the set and
that is the point: B's 183 px are bought at 0.35 diameters of separation, which
means adjacent balls overlap by two thirds and a viewer cannot pick one out of
the eight. The brief's first criterion is size and its third is chosen-colour
tracking; C is the largest composition that keeps the second.

A is the runner-up and the trade against it is 17% of racer diameter for six
frames of holding. It is the safer shot and it is the one to reach for if the
42° elevation reads as a diagram in motion review; the lab builds it from the
same command with `--hook=A`.

Against the shipped opening, measured the same way — a per-racer matte,
rendered, counted:

| | Test #3 | Test #4 (C) | |
|---|---|---|---|
| visible racer diameter @1080 | 59.1 px | **118.4 px** | **×2.00** |
| visible racer diameter @270 | 14.8 px | **29.6 px** | **×2.00** |
| racer area share of frame | 1.06% | **4.28%** | **×4.04** |
| nearest two centres | 1.86 d | 1.05 d | −0.81 d |
| racers, in y | 906 → 983 (77 px) | 523 → 1344 (**821 px**) | |
| racers visible on frame 0 | 8, one clipped | **8, none clipped** | |
| share of a racer's disc on screen | 57% | **92.5%** | |

The separation is the price and it is stated: at 1.00 diameters adjacent balls
just touch on screen and each is still a whole disc of one colour. Below about
0.9 they merge, which is why B is not the answer.

The elevation is 42°, which is high. The brief warns that C "must not become
map-like", and the reason it does not is that the lens is 18° and the stand
fills the frame: what the height buys is the *slant*, which puts the row
across the portrait frame's long axis instead of its short one, and that is
where the extra 25 px comes from.

## 8. The handoff into Camera A

One shot, one move, no second cut.

The opening runs 0.017 → 2.217 s, exactly the frames the shipped `release` cut
occupies, and lands on **`upper`'s first pose walked back one frame along
`upper`'s own opening velocity**. Measured across the join:

| | |
|---|---|
| position residual | 0.0804 |
| `upper`'s own first frame step | 0.0804 |
| **step ratio** | **1.000** |
| lens residual | 0.0000 |

The cut at 2.233 s is still in the schedule and moves the lens by exactly one
ordinary frame of the shot it is cutting to.
`test_the_handoff_is_one_ordinary_frame_step` holds the ratio to ±0.02.

### 8.1 The aim follows the field, and that is not a refinement

A straight interpolation from the hook pose to the handoff pose holds the empty
stand while the field falls out of frame. Measured on the delivered replay it
leaves **no racer on screen at all between 1.1 s and 2.0 s** — nearly a second
in which a viewer who has just picked a colour has nothing to follow, which is
the one failure the brief names by itself.

So the pack's own centroid, read off the replay on the film's frames, is blended
into the aim from 0.20 s to 0.60 s, and the handoff aim is blended back over it
only in the **last 18%** of the shot. That last number is a measurement too:
blending the handoff over the whole eased progress puts the aim 70% of the way
to `upper`'s first frame by 1.3 s while the pack is still accelerating away, and
the field's centroid then runs out to x = +2.3 of a frame that ends at 1.0.

Two instruments, and they answer different questions. *In frustum* is whether a
racer's centre projects inside the frame — a property of the camera alone.
*On screen* is whether any of its pixels survive to the delivered frame — the
camera **and** everything in front of it.

| in frustum, over the opening cut | shipped `release` | V33 straight lerp | **V33 following** |
|---|---|---|---|
| frames with all eight | 70 of 133 | 42 | **105** |
| frames with none | 0 | **55** | **0** |
| fewest in any frame | 7 | 0 | **3** |

| on screen, rendered | Test #3 | **Test #4** |
|---|---|---|
| frames with all eight | 42 of 121 | **108** |
| frames with none | **15** | **0** |

The two tables together are the diagnosis of §3. The shipped opening never
loses a racer *from frame* — its camera is fine. It loses them for a quarter of
a second because the field falls **through the floor it is standing on and
behind the module's own structure**, and nothing was there to see past. That is
an argument for a stand, not for a different lens, which is what this pass
built.

| lens dynamics | shipped `release` | **V33 following** |
|---|---|---|
| max aim turn | 97.7 °/s | 121.8 °/s |
| mean aim turn | 46.8 °/s | **30.5 °/s** |
| max lens speed | 48.9 u/s | **10.7 u/s** |

The 121.8 °/s peak is inside the V31 track's own measured ceiling of 126 °/s,
and the last six frames decay to 2.9 °/s, so there is no whip into the join.

## 9. The finish stand

`race2.bookends.FinishStand`, sited at the sprint's exit on the run's own
tangent. Three jobs:

* **destination** — a gantry straddling the line, the tallest object on the
  stage, with its legs clear of the channel and its header clear above it,
  and a four-portal colonnade reaching back up the channel to meet the lens
  (§9.3);
* **crossing** — a warm inlay *set into* the running surface, with raised kerbs
  only outboard of the channel;
* **somewhere to go** — a plaza laid in strips on the deck the field actually
  rolls onto, a parapet, a catch wall, and a pocket for the racers the deck
  does not catch.

### 9.1 The line is track-integrated because it has to be

The first build put a kerb across the channel at the line, 0.11 proud of the
deck. `clearance` measured it at **0.000** from a racer: a 0.57-diameter ball
rolling down a channel meets a 0.11 step as a wall. The inlay is now set into
the running surface at the cradle's own floor height and declares `touch` —
a racer is *supposed* to be in contact with the line it crosses. Everything
raised is outboard of the channel, where nothing races.

### 9.2 The plaza is laid in strips, and the reason is a fall

The run-out deck falls 1.4° across its width — 0.20 of a unit from the line to
the far edge. One flat plate over it either floats at the low end or swallows a
racer at the high one, so the plaza is twelve bands, each at its own band's
surface height. The step between neighbours is under 0.03 and is invisible at
270 px wide.

The near half of the plaza exists only downstream of `along = 0`, because the
volume at `across ≈ 0` and `along < 0` is the racing channel.

## 10. The defect the finish measurement found

**Race #2's run-out deck is laid across the direction of travel, and the winner
spends the last 3.3 seconds of the shipped film frozen in mid-air.**

`race2.parts.RunOut.__init__` does this:

```python
yaw = math.radians(sprint.heading_deg(exit_index))
self.forward = (math.cos(yaw), 0.0, -math.sin(yaw))
```

`TrackRun.heading_deg` is `atan2(forward.x, forward.z)`. The inverse of *that*
is `(sin yaw, 0, cos yaw)`. The expression above is the inverse of
`race2.kit.Frame.yaw`, which is `atan2(-forward.z, forward.x)` — a different
convention in the same package. The two differ by **90 degrees**.

So on SWITCHYARD, whose sprint runs in −X at a constant z = 24:

* the deck is laid from z = 24 **to z = 32.2** — it extends sideways;
* its 1.4° fall drains the field sideways with it, which is why six racers end
  up 3 to 8 units off the racing line;
* and its near edge **is the racing line itself**, so the half of the exit
  width at z < 24 has no floor at all.

Measured on the replay, in the finish site's own frame:

| racer | state at 19.15 s | along | up | across |
|---|---|---|---|---|
| 0 | running | 3.58 | −0.31 | −3.17 |
| **1** | **escaped** | 3.16 | **−1.79** | −0.11 |
| 2 | running | −4.33 | −0.43 | −7.92 |
| 3 | running | 0.27 | −0.38 | −5.88 |
| 4 | running | 4.51 | −1.23 | 0.77 |
| 5 | running | −1.44 | −0.43 | −7.80 |
| 6 | running | 4.28 | −0.43 | −7.81 |
| **7** | **escaped** | 2.86 | **−1.75** | 0.73 |

m7 is the winner. It crosses at 15.817 s, falls off the end of the channel into
the quadrant with no floor, and at y = −2.35 leaves the machine's own bounding
box — `Aabb.contains(position, slack=MARBLE_RADIUS)` with a lower bound of
−2.04 — and is retired `escaped`. Its velocity is exactly zero from 16.0 s to
the last frame of the film. **The PINK WINS card is composited over a marble
hanging motionless in space.**

The physics is locked, so none of this is fixed here. It is measured, the
scenery is put where the racers actually are, and
`test_the_run_out_deck_defect_is_recorded_not_fixed` fails if anybody re-sites
`RunOut` without re-measuring the finish stand — which is the right fix in a
branch that is allowed to move the race, and is not this one.

### 10.1 The pocket

The well is the region the physics deck does not cover, sized on the frames
that fall through it: `along` 0.73 → 5.20, `across` −0.12 → 1.36, floor at
−2.11. Both frozen racers rest on that floor, so in the picture they are
sitting in a receiving pocket instead of hanging in space.

Its **near edge is clamped to the deck's own edge**, not padded symmetrically
around the fallen racers. Padding put the lip 0.69 inside a deck that is
holding six other racers up, and they then float over a hole — 15 racer-frames
of it. Clamped, the count is **1**, and that one frame is a racer at the apex of
a bounce on its way in.

The pocket has three walls, not four. Its far side *is* the deck edge; a wall
there has nowhere to stand but inside the volume, and built either way it
buries m1, which comes to rest 0.01 outside the edge.

### 9.3 The approach colonnade, and why the gantry alone cannot work

The gantry stands at the line. The final chase frames the **pack**, which for
most of the sprint is twenty units short of it. Projected on the delivered
camera track, at 15.0 s the gantry's corners land at x ∈ [−6.78, −4.33] on a
frame that runs [−1, 1] — **four and a third frame-widths off to the side**,
and off *sideways*, so no amount of height brings it in.

The brief's rule is that the environment adapts to the camera. So the finish
reaches back up the channel: four portal frames at 4-unit intervals, each
shorter than the one in front of it, standing on the racing line's own height
rather than on one datum.

**They stand on the channel, not on a datum.** The sprint descends 0.284 per
unit of `along`; eight units up the channel the racing line is 2.27 higher than
it is at the finish, and the first build's four portals on one datum put a beam
at 0.000 from a racer. `Field.channel(along)` is measured off the run and each
portal is raised by it.

**They are cantilevers.** The final chase's lens is on the negative-`across`
side for all 389 frames of the last cut — it never crosses the channel — so a
leg on that side is a leg between it and the racers. Omitting it took the
sprint's occlusion from 444 racer-frames to 44.

Measured on the difference between the candidate and the control — every pixel
that differs is the stand, its shadow or something it is lighting — the finish
architecture first holds 1% of the frame and keeps holding it at **12.767 s**.
That is 0.08 s into the final chase and **3.05 s before the winner crosses**.
With the gantry alone the same measurement gives 15.517 s, a lead of 0.30 s.

The build from there is continuous, which is what "suspense without a cut"
means in numbers:

| | share of the frame that is finish architecture |
|---|---|
| 12.767 s — first held | 1.6% |
| 15.817 s — the winner crosses | **44.1%** |
| 17.267 s — the payoff | **79.2%** |

No cut was added to get that. The final chase is the shipped one, frame for
frame, and what changed is what it is pointed at.

### 10.2 The sight corridor: the plaza cannot be a lid

A plaza over the whole run-out hides the pocket, and the pocket holds the
winner. Measured on the delivered camera track, a solid plate puts `plaza_7_0`
between the lens and **m7 for 175 frames — 2.9 seconds, the whole of the payoff
card**. V32's finish is built on m7 being on screen continuously from 15.23 s.

So the plaza is cut where the camera looks through it. For every frame of the
last cut and every racer below the deck, the ray from the lens to that racer is
walked until it crosses the plaza plane; the union of those 377 crossings is
`along` 0.97 → 4.80, `across` −1.88 → −0.12, and the plaza leaves that
rectangle open.

The cut costs about a hundred racer-frames in which a racer in *transit* crosses
an opening rather than a plate. That band is where no racer comes to rest — the
six that stay on the deck all finish at `across` ≤ −3.17 — and in the shipped
film it is open anyway, because Race #2's run-out deck is drawn backfacing and
is not on screen at all. The corridor is therefore no worse than what Test #3
delivers there, while the winner being hidden would be strictly worse.

With the corridor cut, the gantry moved 0.92 upstream so the field crosses
*under* the arch, and the colonnade cantilevered, the whole final chase carries
**44 racer-frames of bookend occlusion out of 3112**, and the winner's own share
is **8 frames** — four pairs of two, each one the marble passing under an arch.

## 10a. The payoff card moves, and it is supposed to

`PINK WINS / 5TH -> 1ST` is V32's card, built by V32's code, with its type, its
lozenge, its 3.09:1 contrast and its 1.0 s recognition beat untouched.

Its **position** changes, and that is the mechanism working rather than a
redesign. `presentation.card_band` measures the usable rows on the delivered
frames under two conditions — no row may exceed 130 luma across the text
corridor, and no row may carry a marble that has not finished. On Test #3 the
darkest qualifying band is at the top of the frame, because the top of the
frame is an unlit room. On Test #4 the top of the frame is a pale plaza, so the
band the same rule finds is **y 1455-1680**, at the foot.

The card is therefore at the bottom of this film and at the top of the last
one, with no edit to the card. V32.1 hit the same thing for the same reason
when it drew the running surface; the instrument exists so that a change to the
picture moves the mark instead of colliding with it.

## 11. Bookend coherence

Both stands are built from one `Palette` — graphite base, soft-graphite frame,
pearl edges, a deep-silver deck, a matte mid-grey backdrop, chrome for the
moving rail, restrained gold for the accents, one lit line each. Thirty-nine
parts at the start and sixty-four at the finish, from the same nine keys. A caller that wants a different machine
language names the surfaces it is changing and inherits the rest.

The finish is the more important of the two and the difference is scale rather
than vocabulary: the start's portal rises 2.66 above its deck, the finish's
gantry 4.10 above the line, and the finish carries a warm accent under its
header where the start carries only a cap.

## 12. Reusability

`race2.bookends` knows nothing about SWITCHYARD, seed 8 or eight racers.

```python
site  = bookends.start_site(course)          # or site_from_run(path, i, w)
stand = bookends.start_stand(site, bays, pitch, release_time, release_duration)
```

`start_site` and `finish_site` read a `Course`; `start_stand` and
`finish_stand` take a `Site`, a racer count, a pitch, a palette and a measured
`Field`. A second race course gets its bookends from the same two calls, and a
course that is not a `race2.course.Course` reaches them directly with a site
built by `site_from_run`.

**`site_from_run` takes a tangent, never a heading.** Given §10, that is not a
stylistic preference: differencing two path samples cannot express the mistake
that put the run-out deck at right angles to the race.

---

## 13. The hook text

**PICK YOUR COLOR**, in V32's two-line block, at V32's timing: up on frame 0
with no fade in — a `fade=t=in` starting at zero makes the first frame
transparent, and the first frame is the one the mark exists for — and gone by
1.30 s, which is 0.93 s before the film's first cut.

### 13.1 Bigger racers cost the mark some height

The mark is fitted to the band between the frame's own gutter and the topmost
racer pixel, so a composition that fills more of the frame with racers leaves
less for text. Measured on the delivered plates:

| | V24 | V31 preview | V32 / Test #3 | **V33 / Test #4** |
|---|---|---|---|---|
| lines | 1 | 1 | 2 | 2 |
| size | 96 pt | 104 pt | 201 pt | 127 pt |
| cap height | 71 px | 77 px | 148 px | 94 px |
| **cap at 270 × 480** | 17.8 px | 19.2 px | **37.0 px** | **23.5 px** |
| clear air to the nearest racer | — | — | 200 px | **128 px** |
| band available | — | — | 96 → 736 | 96 → 453 |

Test #4's mark is 36% shorter than Test #3's and still **32% taller than V24's
and 22% taller than V31's**, on a frame whose racers are twice the diameter.
That is the trade the pass makes, stated rather than buried: the racers are the
hook and the words are the caption.

`PICK A COLOR` is built as a second edition from the same frames so the wording
is the only difference between them, and `presentation.hook_placement` sizes and
places both by measurement rather than by a constant: the block is centred in
the band between the frame's own gutter and the topmost racer pixel less V24's
70 px clearance, so the mark cannot cover the eight things it is pointing at on
either wording.

**The mark is fitted against this film's camera, not the shipped one.**
`race2_v32_short.CAMERA` is what `_paths` reads and what `hook_placement`
measures the racer band through. Repointing only the frames leaves the mark
fitted above racers at y 806 — where the *shipped* opening puts them — while
this film's topmost racer is at y 523 and the block's own ink runs to 608. The
first build did exactly that, and its report printed "racers at y 806" over
frames that said otherwise: a placement measured against the wrong film is
wrong in a way that every number in the report agrees with.

**Overriding the wording is not a module global.**
`presentation.hook_placement(..., lines=HOOK_LINES)` binds that tuple when the
module is imported, so setting the global afterwards changes what a reader sees
and not what the function uses — the plate would have said PICK A COLOR while
every report said otherwise. The call site is wrapped instead.

## 14. Render neutrality: the seam is inert

The claim that a new `--bookends=` flag and one `if path.is_empty(): return`
change nothing while they are switched off is worth an experiment rather than a
reading.

A temporary worktree at `157c818d` renders eight instants of the film —
frames 0, 60, 300, 600, 900, 1000, 1100 and 1149 — with the same command line
this branch runs, and the two sets are compared by SHA-256.

    neutrality: 8/8 frames byte-identical to 157c818d4bbda65bf98ddc699b6dd8f9348295f4

Byte equality rather than an image difference, because two renders of one scene
on one GPU are deterministic here and anything short of identical would be a
finding. `stage_neutrality` raises if the count is not complete, so the pipeline
cannot deliver a candidate whose control has drifted.

## 15. The middle, differenced frame by frame

"The middle is unchanged" is asserted four ways in §2 and measured here. Every
fifth frame from 2.233 s to 12.683 s, the candidate against the control:

| | |
|---|---|
| frames sampled | 126 |
| **byte-identical to the control** | **95 of 126 (75.4%)** |
| the one frame over 2% | frame 134 — 2.2333 s, 23.9% of pixels |
| the rest of the non-identical frames | 6.07 s → 8.23 s, 0.62–1.02% of pixels, mean absolute difference 0.15–0.27 of 255 |

Both populations are explained rather than tolerated.

**Frame 134 is the first frame of `upper`** — one frame after the handoff, with
the camera still looking back at the start stand it has just left. That the
stand is in that frame is the pass working.

**The 6.07–8.23 s window** is a 188 × 206 px region in the upper middle of the
frame in which the candidate is *darker* than the control: mean RGB 13.8
against 25.5. It is the finish gantry's silhouette, seen across the hall from
the `upper` shot, against an already-dark part of the room — about 0.9% of the
frame at 11 luma of separation. It is architecture that exists, seen from far
away, and it is the price of a destination that is visible before the racers
reach it.

Nothing else in the middle differs by a single pixel.

## 16. Phone review — 270 × 480

95% of the watch time is mobile, so every proof in this pass carries the phone
size. `docs/validation/race2/v33_bookends/phone/` holds four sheets — the
opening and the finish, Test #3 and Test #4 — sampled by **frame index off the
renderer's own PNGs**, never by `-vf fps=`, which V32's review found returns
frames that are not the ones it names.

**Start, at 270 wide.**

* *Can I instantly see eight competitors?* Yes. Eight discs of 29.6 px on a
  270-wide frame, each in its own bay, against a pale backing panel. Test #3
  offers 14.8 px discs of which 43% is hidden.
* *Can I choose one?* The nearest two centres are 1.05 diameters apart, so no
  two racers touch. This is the measurable cost of the pass: Test #3's row is
  1.86 diameters apart, and the trade is stated in §6.1 rather than hidden.
* *Does the gate movement read?* The rail spans the full bay row and drops
  0.62 over 0.16 s starting at 0.10 s. At 270 px the rail is about 4 px deep,
  which is small; §18 keeps this on the list.
* *Can I keep following that colour after launch?* Every frame of the opening
  shot has at least three racers in it and 105 of 133 have all eight. The
  shipped opening has 55 frames with none.

**Finish, at 270 wide.**

* *Can I see the destination before the crossing?* The architecture is
  continuously on screen from 12.72 s, 3.10 s before the winner crosses.
* *Can I tell who wins?* The winner is clear of every bookend for all but 8
  frames of the final chase, and each of those is a 2-frame pass under an arch.
* *Does the gantry stay readable?* It straddles the channel with 1.16 of
  clearance each side and 3.44 above, so the racers pass through it rather than
  behind it.
* *Does the payoff stay clean?* `card_band` re-measures the usable rows on
  *these* frames rather than inheriting V32's, and the card is built by V32's
  own code from that measurement.

## 16a. What shipped

```
exports/race2_v33_bookends/
  race2_switchyard_v33_your.mp4               the Test #4 candidate
  race2_switchyard_v33_your_phone_270x480.mp4
  race2_switchyard_v33_a.mp4                  the wording comparison
  race2_switchyard_v33_a_phone_270x480.mp4
  compare_opening_1080.mp4                    Test #3 | Test #4, 0 - 3 s
  compare_opening_270x480.mp4
  compare_finish_1080.mp4                     Test #3 | Test #4, 12.68 s - end
  compare_finish_270x480.mp4
  compare_full_1080.mp4                       the whole film, side by side
  your/ and a/                                V32's master, visual and phone cuts
```

| | |
|---|---|
| race | SWITCHYARD, hero seed 8, replay digest `751031348936…` |
| camera | V33 opening (composition C) + V31 RB from 2.233 s |
| environment | `contained_bay_v301`, untouched |
| track | V31.1 variant B, double-faced, untouched |
| frames | **1150**, frame 0 to 1149, contiguous, 0 temporal omissions |
| runtime | **19.1667 s** at 60 fps |
| winner | **m7 PINK**, crosses 15.8167 s, 0.0667 s clear of second |
| payoff | **PINK WINS / 5TH → 1ST**, 16.817 → 19.167 s, contrast 3.09:1 |
| ring | m7, 15.817 → 16.500 s, 42 frames, 0 blocked by the course |
| soundtrack | the delivered V32.2 AAC stream, copied |
| qc | `docs/validation/race2/v33_bookends/qc.json` |

`race2_v33_bookends.py qc` re-measures every one of those on the delivered
files rather than on the plan, including the frame count — see Appendix A for
why that check earns its place.

## 17. Remaining weaknesses

Named rather than left for the next reader to find.

1. **The separation cost is real.** The chosen hook puts adjacent racers 1.05
   diameters apart against the shipped opening's 1.86. Nothing overlaps, but
   the row is tighter and a viewer scanning for "the third one from the left"
   has less air to do it in. The only way to buy it back is distance, and
   distance is the thing the pass exists to spend.

2. **The gate is small at 270 px.** It is unambiguous at 1080 and about four
   pixels deep on a phone. It cannot be made taller without entering a sight
   cone (§5), so if the gate needs to read harder the answer is a different
   *kind* of motion — a colour change, a light, or segmented doors that open
   outward — rather than a bigger bar.

3. **The elevation is 42°.** C is the largest composition that keeps its
   separation, and it gets there partly by looking down. It is not map-like
   because the lens is 18° and the stand fills the frame, but it is the highest
   hook this film has had, and a viewer who reads the first frame as a diagram
   rather than as a grid is reading it the way the angle invites.

4. **The winner still ends the film motionless in a hole.** The pocket makes
   that legible instead of absurd — it is now a racer resting in a receiving
   well rather than a racer hanging in space — but the underlying fact is a
   physics defect (§10) and only a branch allowed to move the race can fix it.

5. **The finish gantry is visible from the `upper` shot** for about two seconds
   in the middle of the film, at 0.9% of the frame and 11 luma of separation
   against a dark wall (§15). It is faint, it is architecture that genuinely
   exists, and it is still a difference in a window the brief asked to freeze.

6. **One racer-frame floats over the pocket** and about a hundred cross the
   sight corridor in transit (§10.2). Both are measured, both are in a band
   that is already open in the shipped film, and neither involves a racer at
   rest.

## 18. Test #4, and what it is a test of

**The recommendation is to run it**, as the `PICK YOUR COLOR` edition, against
Test #3 with nothing else varied.

What the experiment is entitled to conclude, and what it is not:

* If **stayed-to-watch** rises toward Test #2's 41.7% while the **share viewed**
  holds near Test #3's 70%, the diagnosis in §1 was right and the bookends are
  what was missing. That is the hypothesis this branch was built to test and
  every lock in §2 exists so that a rise can be attributed to it.
* If stayed-to-watch rises and share-viewed *falls*, the opening is buying
  attention the middle cannot keep, and the next pass belongs in the middle
  rather than at either end.
* If neither moves, the opening was not the constraint, and the honest next
  step is the thing this pass deliberately did not touch: the race itself.

A second edition with `PICK A COLOR` is built from the same frames so the
wording can be tested on its own later. It is not part of Test #4 — one variable
at a time is the whole point — and it exists so that the comparison is one
command rather than one branch.

### What did not change

Physics, replay, seed, winner, finish order, runtime, mechanism timings, the
three later camera cuts, the course, the environment, the track profile, the
palette, the payoff card, the winner's ring, the hook's timing, and the
soundtrack — which is the delivered V32.2 AAC stream, copied.

### What did

One opening shot, two stands, and 44 racer-frames of the final chase in which a
marble passes under an arch.

---

## Appendix A — two flags that were silently wrong

Both were caught by measurement rather than by review, and both would have
shipped.

**`ffmpeg -shortest` on a stream copy dropped a frame.** The soundtrack is
920000 samples — exactly 1150 frames at 48 kHz — and the picture is 1150
frames, but the AAC container rounds its duration to 19.166 s against the
video's 19.1667 and is therefore marginally the shorter stream. With
`-shortest`, ffmpeg truncated the *video*. It did so on one of two otherwise
identical muxes and not the other: the `PICK YOUR COLOR` edition came out at
**1149 frames and 19.150 s** while `PICK A COLOR` came out correct. A flag that
is wrong intermittently is worse than one that is wrong always, and the only
reason it was found is that `qc` counts frames on the delivered file rather
than trusting the command line.

**`drawtext` is not available and fails loudly in the wrong place.** The
comparison videos' captions needed fontconfig, which ffmpeg on this machine
reports as `Cannot load default config file` before exiting 2 — a comparison
that silently did not build. The project already owns a font resolver in
`sloped.overlays`, so the captions are drawn with PIL and overlaid.

## Appendix B — rebuilding

```
python tools/race2_v33_bookends.py all
```

Fourteen stages, each runnable alone: `field`, `spec`, `camera`, `hooks`,
`master`, `control`, `metrics`, `middle`, `finish`, `short`, `compare`,
`sheets`, `neutrality`, `qc`. `--hook=A|B|C` chooses the composition the full
candidate uses, `--text=your|a|both` the wording, and `--measure-only` re-runs
the arithmetic with no render at all.

Godot is found through `--godot`, `$GODOT_BIN` or the PATH, in that order. The
soundtrack is read from the delivered V32.2 Short, which is in `exports/` and
therefore not in git; the lab says so by name rather than silently rebuilding
one.
