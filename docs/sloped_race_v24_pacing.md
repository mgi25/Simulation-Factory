# V24 — the pacing lab: a tighter Short, cut from the V22.1 picture

**TIMING PROOF ONLY.** Everything in this pass is the V22.1 master with whole
frames taken out of it. The lenses, the framing, the grade and the hook are
V22.1's, and none of them is a proposal. Session A owns the hook composition; a
still from any clip here is a still of V22.1. What is proposed is **when things
happen**.

Branch `v24-pacing-lab`, from `origin/main` at `e697a12`. Nothing in
`sloped/presentation.py`, `sloped/cameras.py`, `tools/sloped_short.py` or
`tools/sloped_short_qc.py` is touched. Three files are added:

    sloped/v24_timeline.py            the model, the inventory and the checks
    tools/sloped_v24_pacing.py        machine / survey / report / clip / verify
    tests/test_sloped_v24_pacing.py   34 tests

---

## 1. What was asked and what came back

V22.1 went up at 26.533 s: 19.6% stayed to watch, average watch ~24 s, roughly
89% viewed. The race body is holding people. What it is asked to hold them
*through* is 3.500 s of course preview at the front and 3.617 s of machine after
the winner crosses.

The brief asks for **18.5–20.5 s**, no course preview, honest whole-frame
omissions only, and three start timings to compare.

|  | runtime | frames | omissions | start → downhill | time to release | first race action | winner | after winner | crossings | replay coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **A** compact start | 19.600 s | 1176 | 5 | 3.900 | 3.650 | 4.071 | 17.533 | 2.067 | 5 / 8 | 83.7% |
| **B** balanced — **recommended** | 19.867 s | 1192 | 5 | 4.067 | 3.750 | 4.237 | 17.700 | 2.167 | 5 / 8 | 84.1% |
| **C** richer start | 20.233 s | 1214 | 3 | 4.533 | 3.933 | 4.704 | 18.167 | 2.067 | 5 / 8 | 86.0% |
| *D — rejected* | *18.533 s* | *1112* | *3* | *2.733* | *2.483* | *2.904* | *16.367* | *2.167* | *5 / 8* | *78.7%* |

All three land inside the band, none of them is 20.000 exactly, and all three
pass every check. D is not on offer — see §6.

The preview alone is 3.500 s of the 3.2–3.4 s saved, and it costs nothing to
remove: it is separate footage joined by `concat`, so `Clock.prefix` goes to
0.0 and the film starts on the held race frame.

---

## 2. The one honest operation, and the one place it was not available

Two things happen to the master and nothing else: **whole frames are dropped and
the gap closes**, and **the master stops early**. No speed change, no
interpolation, no blending, no repeated frame, no physics. Every surviving frame
keeps the replay instant it always had.

`presentation.omit_frames` is production's function for the first of those and
this pass **does not use it**, because it cannot represent the cuts V24 needs.
It emits one segment per window of the edit map. That is right for every cut
production has ever made — V21.1's `49..133` trims one window's tail and the
next window's head, so each window's survivors stay contiguous — and it is
wrong, silently, for a cut in the *middle* of a window:

    a 100-frame window, replay 0.000–1.650, omit master frames 30..59
    omit_frames returns one segment   (0.0, 1.15, 0.0, 1.65)

1.15 s of output carrying 1.65 s of replay is slope **1.43**. Every frame after
the cut is mis-dated by up to 0.500 s, and `at(0.700)` hands back an output
second for a replay instant the film does not contain. Three of V24's five cuts
are interior, so `v24_timeline.build` emits **one segment per contiguous run of
kept frames** instead — slope 1 by construction.

This is a latent defect in production code, not a V24 one, and this pass does
not fix it: the brief says do not modify `presentation.py`.
`test_omit_frames_cannot_represent_an_interior_cut` pins it, and says in its own
docstring that when it starts failing the workaround can be deleted. See §9.

---

## 3. Which frame is which, settled from the pixels

Every cut in `cameras_v221_5432.json` repeats its boundary row — cut 0's last
entry and cut 1's first are both at output 1.850 — so 1347 rows become 1340
rendered frames, and which row the renderer dropped decides what replay instant
every master frame after the first boundary shows. The two readings differ by
one frame everywhere, which is the size of the errors this pass measures.

It was settled by looking. The start lens hands to the chase at replay 6.700 and
that is the master's one hard lens change, so it is a spike in the frame-to-frame
difference:

    master 271→272   mean |dpix|   2.416
    master 272→273   mean |dpix|   2.420
    master 273→274   mean |dpix|  56.046      ← the lens change
    master 274→275   mean |dpix|   0.857

The renderer drops the **first** row of every cut after the first, so master
frame `f` shows what `presentation._window_of` assigns to output `f/60` —
production's own reading. `load_master` rebuilds the pose list that way and
raises if it and the edit map ever disagree by a single frame.

---

## 4. The bar, and the units a teleport is measured in

An omission is not good or bad in the abstract; it is better or worse than one
the audience has already accepted. V22.1's `b116` start omission is that
reference, measured on the delivered master:

|  | |
| --- | --- |
| marbles move | 0.50 wu — **34.6 px** mean, 84.3 worst |
| in marble widths | **0.47** mean, 1.12 worst |
| camera steps | 0.054 layout units — one frame of its own orbit |
| a normal one-frame step nearby | 1.0–1.8 px |

**Marble widths on the delivered 1080×1920 frame is the unit**, not world units,
because the chase camera moves with the field. A 30-frame omission moves the
field 7.8 wu in the descent and 1.6 wu in the trap — a factor of five — but 1.56
and 0.95 marble widths, a factor of 1.6. The pixels are what a viewer sees.

`MARBLE_WIDTH_BAR` is 1.20: the shipped join with room.

### What a 30-frame omission costs, best placement in each window

| window | replay | px mean | marble widths | camera steps | machine |
| --- | --- | --- | --- | --- | --- |
| start (drum) | 0.200→0.717 | 58.2 | 0.73 | 1.764 | **illegal** — the gates move 1.088 units across it |
| start (ceremony) | 4.433→4.950 | 9.7 | 0.13 | 1.642 | **illegal** — rotor 13.00 → 0.04 rad/s |
| descent | 6.800→7.317 | 81.8 | 1.56 | 6.931 | legal |
| obstacle | 13.933→14.450 | 73.4 | **0.95** | 0.759 | legal |
| fork | 15.117→15.633 | 102.4 | 1.72 | 9.528 | legal |
| branches | 16.733→17.250 | 228.5 | 5.81 | 9.545 | legal |
| final | 23.917→24.433 | 181.5 | 3.16 | 0.000 | legal |

Two things fall out of that table. **The two cheapest-looking omissions in the
whole film are both illegal** — they are cheap precisely because the marbles are
not moving, which is also when the *machine* is doing something. And **the
obstacle is the only affordable place in the race body**; everywhere else the
chase camera is flying and an omission moves the whole frame. The finish is the
worst of all — the marbles are closest to the lens there, and a 45-frame cut
moves one of them 1235 px — which is why the finish gives time back by
**stopping**, not by skipping.

---

## 5. The rotor is the constraint, and it is arithmetic

The drum spins four identical blades at 13.0 rad/s — **12.4139° a frame**. An
omission inside that spin is invisible only if the blades come back where the
next frame would have put them: the gap in frame steps, less the one step a join
is entitled to, must be a whole number of quarter turns. A quarter turn is
7.2498 frames at 60 Hz, so only whole revolutions land near an integer, and one
revolution is **29 frames** (360.03°, 0.03° of error).

### The shipped join is one frame off its own lock

`v221_shuffle.PLANS["b116"]` asks for `cut_at=2.05, resume_at=4.0` — 117 frame
steps, four exact revolutions. But replay 4.000 is the duplicated boundary row
the renderer drops, so the film resumes on 4.016667 and the gap is **118** steps.
The blades step 24.86° across the join where a frame step is 12.41: one extra
frame of rotation, **12.44° of phase error**, where V22.1's own report claims a
hundredth of a degree.

It is under the noise and not worth fixing — the pixels agree, the join differs
by 4.09 where its neighbours differ by 3.3–3.5 — but it changes the arithmetic of
*extending* that omission. Adding a whole revolution keeps the 12.44° error.
Adding **28** frames makes the gap 146 steps, 145 of which is five exact
revolutions, and the blades land within **0.04°**. The extension is a frame
shorter than the thing it extends.

### The drum shot's tail cannot be trimmed, and the reason is three frames

Resuming at master frame 140 needs `256 − last ≡ 0 (mod 29)`, so the last drum
frame can only be **111, 82, 53 or 24**. The rotor does not take hold until
replay 1.6167, which is **master frame 85**:

| drum ends | replay | marbles | machine |
| --- | --- | --- | --- |
| 111 | 2.0500 | 0.53 widths | same state ← shipped |
| 82 | 1.5667 | 0.89 | 0.00 → 13.00 rad/s |
| 53 | 1.0833 | 2.32 | 0.00 → 13.00 rad/s |
| 24 | 0.6000 | 4.16 | 0.00 → 13.00 rad/s |

82 misses by three frames. There is no legal trim of the shuffle shot at any
setting. `DRUM_FALSIFIED` records it, unused, because "trim the shuffle" is the
first thing the next pass will reach for.

### The one place a time skip is free

A join placed on an **existing lens change** costs nothing new — the film
already cuts there. Measured with nothing omitted, the start→chase boundary
already moves the marbles 162.7 px (2.51 widths) and the camera 19.3 layout
units. Omitting 21 further frames into it moves them **158.4 px, 2.38 widths** —
slightly *less*. So the start shot may end early and let the chase pick the field
up, and the bar does not apply to that join; it is measured against the
unmodified boundary instead.

---

## 6. The start: what is reachable, and what the brief asked for

The brief asks for start timings around 2.2–2.5, 2.7–3.0 and 3.2 s. **The V22.1
master cannot reach any of them without breaking something the last pass fixed.**

The start's whole slack is 76 frames, 1.267 s, against a 5.267 s start:

| | frames | replay | marbles | why it is legal |
| --- | --- | --- | --- | --- |
| `SPIN` | 28 | 4.017–4.467 | 0.53 widths | five exact revolutions |
| `STOPPED` | 16 | 4.933–5.183 | 0.10 | rotor halted, blades still down |
| `ANTICIPATION` | 11 | 5.683–5.850 | 0.07 | blades up, floor shut, nothing moves |
| `FALL` | 17 | 6.433–6.700 | — | on the existing lens change |

The spin-down (4.617–4.917) and the blade lift (5.217–5.650) are machine motion.
An omission across either changes the machine's state in a single frame, which is
exactly the defect V22 shipped and V22.1 was written to fix — the note that came
back about V22 was *"the shuffle still looks cut"*. `machine_match` refuses those
cuts rather than offering them.

So the floor is **3.90 s to the descent lens** and **3.65 s to the trapdoor**,
and the three candidates span 3.90 → 4.53 and 3.65 → 3.93.

Two boundary details worth keeping: `STOPPED` ends at master 182 rather than 183
because 183 is replay 5.200 and the blades leave the floor at 5.2167; and both
anticipation cuts start at 212 rather than 211 because the blades reach the top
at 5.6667, and frame 210 is 0.0048 layout units short of it. Both are invisible,
and both are transitions a join would otherwise be sitting on.

### D, which reaches the brief and is turned down

`REJECTED["d_rejected"]` takes the whole ceremony out in one omission (master
112..236) and puts the field on the downhill at **2.733 s** — inside the brief's
second band, in an 18.533 s film. It is rendered, labelled, and not on offer:

    output 2.467   125 frames omitted
                   the field moves 0.90 marble widths — barely anything
                   the rotor turns at 13.00 rad/s before the join and 0.04 after
                   the blades stand 1.193 layout units apart across it
                   the blades land +23.57° off the lock
                   and it resumes 0.017 s before the trapdoor opens

The marbles are the thing that does *not* give it away. The machine is.

---

## 7. The race body: approach, interaction, exit

Segment by segment, on candidate B. `run-up` is approach → interaction and
`pay-off` is interaction → exit; every one of the ten is whole in every
candidate.

| segment | run-up | pay-off |
| --- | --- | --- |
| start | 0.117 | 1.733 |
| shuffle | 0.583 | 0.767 |
| release | 0.283 | 0.200 |
| descent | 0.983 | 1.967 |
| obstacle | 1.717 | 3.200 |
| escape | 0.596 | 1.304 |
| fork | 1.183 | 3.050 |
| branches | 1.117 | 0.567 |
| merge | 0.483 | 0.467 |
| finish | 1.933 | 0.867 |

**The race body gives up exactly one thing: 0.500 s of the spinner trap**
(replay 13.583→14.100, master 687..716). The trap is churn 3.18–4.75, the lowest
sustained stretch in the body, and the field is being held rather than travelling
— 1.62 wu and 1.11 marble widths across the join, just under the bar.

It is placed against both of the brief's warnings and `check` enforces both:

* the obstacle payoff is replay 11.400–12.650. The cut starts **0.93 s after it
  ends**;
* the leader's escape into `leg3` is 14.9958. The cut resumes at 14.100, which
  leaves **0.896 s** of the field visibly accelerating before the break-out.

Nothing else in the body moves. The descent, the fork, the branches and the merge
are V22.1's to the frame.

### The finish

The brief says keep V22.1's continuous final approach and do not restore the old
hard finish cut. Nothing here touches it — the park is intact and there is no
interior cut anywhere in the final window, because that is the most expensive
place in the film to make one.

What is trimmed is the **tail**. Seed 5432 finishes at 20.850, 21.133, 21.717,
22.633, 22.650, 23.500, 24.317, 24.417. A and C stop at replay 22.900 and B at
23.000 — 0.25–0.35 s after the fourth and fifth arrive **0.017 s apart**, which
is the strongest beat available to end on. That is 2.07–2.17 s of film after the
winner, against V22.1's 3.617 s.

Crossings six, seven and eight are not shown. That is an editorial choice and it
is a dial: `TAIL_SIX` (replay 23.750) puts the sixth back for 0.717 s, and
`TAIL_ALL` restores all eight for 1.567 s. B with `TAIL_SIX` runs 20.583 s,
which is 0.083 s outside the band.

---

## 8. Proof clips

    output/sloped_race_v1/v24/v24_v221_TIMING_PROOF_ONLY.mp4        23.033 s  1382 f  control
    output/sloped_race_v1/v24/v24_a_TIMING_PROOF_ONLY.mp4           19.600 s  1176 f
    output/sloped_race_v1/v24/v24_b_TIMING_PROOF_ONLY.mp4           19.867 s  1192 f
    output/sloped_race_v1/v24/v24_c_TIMING_PROOF_ONLY.mp4           20.233 s  1214 f
    output/sloped_race_v1/v24/v24_d_rejected_TIMING_PROOF_ONLY.mp4  18.533 s  1112 f

Silent, no overlays, no soundtrack, with **TIMING PROOF ONLY** burned into every
frame. The control is the V22.1 picture with only the preview removed, so a
reviewer can see what the candidates are shorter *than*.

`output/` is not in the branch. **The clips live only in this worktree and must
be copied out before it is removed.**

### The clips were verified, not just counted

A frame count only proves the length. `--stage verify` pulls frames back out of
each clip and matches them against the master, including the frame either side of
every join, and asks **which master frame each one matches best** rather than
testing an absolute threshold — both files are lossy encodes of the same render,
so the residual is never zero and is not the interesting number. A clip that is a
frame out matches its neighbour better.

    a            33 frames checked - every sampled frame is the one the plan names
    b            34 frames checked - every sampled frame is the one the plan names
    c            30 frames checked - every sampled frame is the one the plan names
    d_rejected   30 frames checked - every sampled frame is the one the plan names

and the hold is master frame 0 repeated, to 0.011–0.014 mean |dpix|.

---

## 9. Tests

`tests/test_sloped_v24_pacing.py`, 34 tests, all passing. They skip rather than
fail where the replay and the track — generated output, not in the branch — are
absent; the arithmetic tests build their own clock and run anywhere.

| | |
| --- | --- |
| replay monotonicity | every kept frame shows a later instant than the one before |
| no backward frames | frames ascend, appear once, and frame 0 survives (the hold clones it) |
| exact omission boundaries | each cut drops the frames it names and neither neighbour |
| the clock is slope 1 | every segment carries as much output as replay — the defect §2 describes |
| frame-for-frame | `replay_at(origin + n/60)` is master frame `kept[n]`, for every n, in every candidate |
| obstacle payoff retained | 11.400, 11.700, 12.000, 12.300, 12.650 all on screen |
| fork retained | all eight route decisions, 16.300 → 19.350 |
| finish order unchanged | 5, 2, 7, 4, 1, 6, 3, 0 |
| winner unchanged | marble 5 at replay 20.850, first crossing shown, ≥1.5 s of film after it |
| no course preview | `prefix == 0.0`, and frames = hold + kept master frames |
| runtime bounds | 18.5–20.5, and not 20.000 |
| the machine instants | gates, rotor, wind-down, lift and release re-derived from the transforms |
| one revolution is 29 frames | and a join omitting N frames spans N+1 steps |
| the drum trim is falsified | the phase lock and the spin-up are three frames apart |
| joins do not teleport | under the bar, or under the lens cut they sit on |
| no join crosses a transition | the machine's state matches on both sides of every one |
| D reaches the brief and fails | 2.7–3.0 s to the downhill, and four problems |
| `omit_frames` still works | for head-and-tail cuts, and still cannot do interior ones |

---

## 10. Integration instructions

This pass is a **timeline**, not a picture. Nothing here is ready to ship as-is,
and three things have to happen first.

**1. Re-solve the camera track to the chosen bounds.** A phase-exact omission
keeps the *blades* continuous; it does not keep the *camera* continuous.
`v221_shuffle.constant_rate_legs` split the start orbit across the windows the
shipped film has, so dropping 28 more frames steps the lens **1.558 layout
units** where the shipped join steps 0.054. It is visible as parallax across the
join, it is in every proof clip, and it is entirely removable by re-splitting the
legs across the new window — which is a re-render, not an edit. The three other
start joins step 0.61–0.89 units and want the same treatment.

The recommended B, as window bounds for a re-render, in replay seconds:

    start   0.200 – 2.050     the drum, unchanged
            4.483 – 4.917     the last of the constant spin, and the wind-down
            5.200 – 5.667     the blades lifting clear
            5.867 – 6.417     the anticipation, the trapdoor, and into the fall
    descent 6.717 – 9.667     unchanged
    obstacle 9.667 – 13.583   unchanged
            14.100 – 15.100   the escape
    fork    15.100 – 16.733   unchanged
    branches 16.733 – 18.417  unchanged
    merge   18.417 – 18.900   unchanged
    final   18.900 – 23.000   the park, ending after the fifth crossing

**2. Take the hook from Session A.** The 0.700 s hold and PICK ONE are V22.1's,
carried here only so the clock has a front. A is quoted at 0.600 s; both are
inside the 0.6–0.9 band V20 established.

**3. Add the edition to `tools/sloped_short.py`, with no preview.** A V24 entry
is `{"master": MASTER_V24, "cuts": (), "runtime": (18.5, 20.5)}` and **no
`preview` key** — that is the whole of what removing the course flight costs the
edition table, because `prefix` is derived from the preview file's frame count
and is 0.0 when there is none. Every cue moves with the clock: `audio/marble.py`
derives all of them from the edit map, and the two placed cues (the gates, the
trapdoor) come from `actuator_move` on the replay.

**If the master is re-rendered to those bounds, no frames need dropping at all**
and `presentation.omit_frames` is not involved. If instead V24 is cut from the
existing V22.1 master — which is what the proof clips are — then §2 applies and
`omit_frames` must not be used for it until it splits interior cuts.

---

## 11. Weaknesses

**The camera steps at four joins.** §10.1. The largest is 1.558 layout units at
the start's first join; on a 22.9-unit lens that is about 3.9° of arc, which
reads as the drum rotating slightly across the cut. It is a consequence of
editing a rendered master rather than re-solving one, and the proof clips are
honest about it.

**The start is 0.7–1.3 s longer than the brief wants.** §6. The floor is real
and D demonstrates its cost, but the brief's number was not reached and a
reviewer who wants 2.7 s has to accept either a re-render (which could place the
ceremony's own bounds freely) or D's machine cut.

**Only five of eight crossings.** §7. The field trickling in is the tail, but a
reviewer may read three unfinished marbles as an unresolved race. `TAIL_SIX`
costs 0.717 s and `TAIL_ALL` 1.567 s, both of which push B outside the band.

**The trap cut is the closest thing to the bar.** 1.11 marble widths against a
1.20 bar and the shipped join's 0.47. `TRAP_SHORT` is the same placement at 20
frames (0.76 widths) and costs 0.167 s. Nothing in the race body is cheaper;
that was measured across all seven windows and is §4's table.

**The finish's own dead stretch is untouched.** V22.1's report records that the
leaders leave frame for 0.98 s during the park (replay 19.483–20.450) while the
camera waits at the line. That is 59 frames and it is the largest single piece
of low-information time left in the film — but every omission in the final window
costs 3+ marble widths, so it cannot be cut. It can only be fixed by a different
park, which is a camera pass.

---

## 12. Rebuilding

    python tools/sloped_v24_pacing.py --stage all --seed 5432

Inputs, all already on disk and none rebuilt here:

    output/sloped_race_v1/race_5432.json            the locked replay
    output/sloped_race_v1/cameras_v221_5432.json    the V22.1 camera track
    output/sloped_race_v1/v221/race_master.mp4      the V22.1 race master, 1340 frames

The course preview master is deliberately not an input.

    python -m pytest tests/test_sloped_v24_pacing.py -q

The physics is untouched: same seed, same replay, same digest, same eight
crossings in the same order.
