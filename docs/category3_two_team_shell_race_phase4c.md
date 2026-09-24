# Category 3, Test #2 — two-team multiplying shell race
## Phase 4C: framing lock, destruction polish, and the upload-ready master

A human reviewed the Phase 4B clips and rejected the presentation for the
third time. The mechanic has survived every review intact and nothing in this
phase touches it: the simulation's config digest is still
`4a3ab8ba22ae7c54981700823cc5b4eaf147c72fc5ab609a244d9cbaeb6ce572`, the schema
is still `category3-test2-two-team-shell-race/3.0.0`, and the master WAV for
the production candidate re-renders to SHA-256
`f038a1a9b330572484b28adb40e4e9d4b3ea034cbed8f728ece0075c62c30c0e` — the same
file Phase 4B recorded, byte for byte, not merely the same loudness figures.

The five things the review actually asked for:

1. the camera still zooms out too much;
2. the race becomes visually too small in the portrait frame;
3. too much empty dark space remains late in the video;
4. damage still reads as marks and indicators rather than physical destruction;
5. the final break needs a stronger visual payoff.

**Base.** `category3-two-team-visual-impact-v4b` at
`65190b2946e385f1415f970b925818ee70986737`. Branch
`category3-two-team-production-v4c`, worktree `wt-category3-two-team-v4c`. Not
merged. Render config digest `e438b716da30f062`, production fingerprint
`d798fbecb1be5102`.

---

## 1. The camera was still solving a smaller version of the wrong problem

Phase 4A's rule was *fit the whole arena inside the band that clears the Shorts
action rail* and produced 0.652. Phase 4B replaced it with *fit the whole arena
inside the frame* and produced 0.850. The review rejected both, and in
hindsight they are the same rule with a different rectangle: **whatever the
rectangle, an arena that has to fit inside it ends up small in a 9:16 frame,
because a circle in a 9:16 frame wastes both ends.**

The 4C brief drops the rectangle. Cropping is allowed, the full circumference
does not have to be visible, and the objective is that the interesting action
is *large*. So `FRONTIER_WIDTH_FRACTION` is now allowed above 1.0, where the
framed wall's material diameter is wider than the frame and its left and right
caps are off screen on purpose. At the selected 1.200 the outer wall is
**1296 px across in a 1080 px frame**, and a decoded frame from the delivered
master has ink touching x = 0 and x = 1080.

### The A/B/C experiment, on rendered frames

Eleven event-centred stills of seed 17964 at 1080x1920, at each of the brief's
three widths, with the 4B fraction carried as a control. **The sweep varies the
fraction and nothing else** — the 0.850 row is the 4B *framing* with everything
else 4C, so it isolates what the width alone buys. Ink, empty band and white
share are counted off the pixels; ball, opening and wall are derived from the
frustum.

| variant | fraction | mean ink | early ink | late ink | worst empty band | drawn ball | final opening | final wall | hidden | hard classes | ball-frames off frame |
|:--|---:|---:|---:|---:|---:|---:|---:|---:|---:|:--|---:|
| 4B control | 0.850 | 0.456 | 0.504 | 0.402 | 531 px | 33.9 | 35.9 | 57.2 | 0 | pass | 0 |
| A | 1.000 | 0.531 | 0.560 | 0.508 | 479 px | 39.9 | 42.3 | 76.3 | 0 | pass | 0 |
| B | 1.100 | 0.566 | 0.580 | 0.565 | 431 px | 43.9 | 46.5 | 90.4 | 4 | pass | 64 |
| **C** | **1.200** | **0.591** | **0.590** | **0.609** | **382 px** | **47.9** | **50.7** | **105.4** | 7 | **pass** | 132 |

Every column is monotone, so there is no trade to make inside the brief's band:
C is simply the far end of it. The evidence is
`docs/validation/category3_two_team_shell_race_v4c/framing/`, eleven
side-by-side sheets at render resolution plus the per-frame measurements.

**And C is the only variant whose late frame is not emptier than its opening.**
That is the one item Phase 4B could not deliver at all.

### What the crop costs, measured rather than waved through

* **Nothing that has to be seen.** `critical_visibility_report` now measures
  the frame edge as well as the action rail, because above 1.0 the edge is the
  binding constraint and a report that still only looked at the rail would pass
  a framing that cropped the winning escape off the screen. Every hard class —
  the first clone, every panel break some ball later used as a passage, and the
  winning escape — is **0.000 covered and 0.000 off frame at 1.00, 1.10 and
  1.20 alike, on both production candidates.**
* **Ordinary frontier crossings and near misses.** 7 of 17964's 78 crossings
  and 3 of its 27 near misses end up partly hidden at 1.200. On 1176, zero.
* **A ball can be off frame.** It is 8.5% of 17964's frames and 11.6% of
  1176's, and 1.5% and 3.5% of ball-*instants*. Every one is at a horizontal
  cap of the outer region and **every one is after the camera has locked** —
  `contained_while_moving` is true on both. A ball leaving a frame that is
  itself moving is the version a viewer reads as a mistake, and it never
  happens.

The old whole-arena `safe_area_report` now returns `arena_clear: false` and
`ball_pass: false` by construction. It is kept as context and gates nothing;
`critical_visibility_report` is the gate.

---

## 2. One transition, and again the grouping is forced

Phase 4A moved the camera four times, 4B twice, and the brief allows one. The
brief also adds a requirement 4B did not have — *the final 6 to 10 seconds must
be fully static* — and the two together pick the pair with no room for taste:

1. the last stage frames shell 4, because the final wall has to be framed when
   the winner leaves through it;
2. no ball may be outside the frame before the move, so the opening extent must
   cover every region the race reaches first;
3. the move must leave at least 6 s of locked camera. **This is what rules out
   4B's trigger.** Region 4 arrives 4.47 s and 5.52 s before the escape on the
   two candidates, which is why 4B's static tails were 4.16 s and 5.21 s.

Triggering on region 2 — the frontier crossing shell 1 — is the latest trigger
that clears rule 3 on both candidates, and it is a meaningful point: the race
has left the two inner shells and is into the second half of the arena.

    CAMERA_STAGE_PLAN = ((0, 2), (2, 4))      # (trigger region, extent shell)

| seed | transition | lock | static tail | zoom |
|---:|:--|---:|---:|---:|
| 17964 | 4.63 → 5.03 s (trigger 4.77) | 5.03 s | **20.74 s** | 1.474x |
| 1176 | 11.96 → 12.36 s (trigger 12.10) | 12.36 s | **11.41 s** | 1.474x |

**The pleasant arithmetic is that both stages divide by the same fraction**, so
the single move is 12.65 → 18.65 world units *whatever the fraction is*:
1.474x, against 4B's 1.62x first step and 1.933x total. Raising the fraction
made the arena bigger without making the one remaining zoom any larger.

### The transition duration is not a preference

The gate is 4B's: twice the fastest a ball ever crosses the *opening* framing.
It is not slack here, because the 4C opening frames shell 2 rather than shell 1,
so the ball's reference screen velocity is a third smaller and the same move
costs more against it. Measured on both candidates at 60 fps:

| ease | 0.25 s | 0.30 s | 0.35 s | **0.40 s** |
|---|---:|---:|---:|---:|
| screen velocity vs ball | 3.07x | 2.57x | 2.20x | **1.93x** |

0.40 s is the slowest the brief's 0.25–0.40 band allows and the **only** value
in it that passes the 2.0x gate. Every faster value would make the one
remaining move more noticeable than either of 4B's two.

No lateral pan, no shake: `centring_report` returns 0.00 px of lateral and
vertical camera movement and the arena centre is exactly 540 px, half the frame
width. The horizontal crop is symmetric — 108 px off each side — and the arena
still fits *vertically* between the top bar and the title block, so the crop is
one-dimensional. That is asserted rather than hoped.

---

## 3. Empty space, measured the way the complaint was made

The framing sweep measures eleven event-centred stills, which is the right set
for judging composition and the wrong one for judging emptiness: they cluster
where things happen and three of them sit inside the last second. "Too much
empty dark space remains **late in the video**" is a claim about thirds of the
run, so the sample has to be uniform in time. 25 uniformly spaced stills per
candidate, rendered at 1080x1920, at two fractions and nothing else changed:

| seed | framing | early | middle | late | late/early | worst empty band |
|---:|---:|---:|---:|---:|---:|---:|
| 1176 | 0.850 | 0.530 | 0.463 | 0.358 | 0.675 | 531 px |
| **1176** | **1.200** | **0.593** | **0.575** | **0.564** | **0.951** | **382 px** |
| 17964 | 0.850 | 0.467 | 0.356 | 0.357 | 0.765 | 531 px |
| **17964** | **1.200** | **0.583** | **0.563** | **0.564** | **0.969** | **382 px** |

The brief's floor was "late occupancy should not collapse to approximately half
of opening occupancy as before". It is 95.1% and 96.9% of it. The brief's
stretch was "late ≥ middle": 17964 meets it outright (0.564 against 0.563);
1176 misses it by 0.011, which is 1.9% and is what "remains visually
comparable" means. The tallest band of frame with no ink at all falls from
531 px to 382 px, a 28% cut where 4B managed 8%.

The analytic model in `occupancy_report` still says late < early on both
candidates (0.271 against 0.384 on 1176). It is not wrong and it is not the
answer: it counts a panel's whole analytic annulus and no glow at all, and the
brief says the rendered frame is authoritative. Both numbers are in the
evidence and neither is quoted alone.

---

## 4. Damage that happened to the material, take three

Phase 4A drew up to six bright bars at the first six impact offsets; the review
called them UI annotations. Phase 4B made each one a dark pit with a bright
hairline in it; the review said it still reads as red and pink marks. Two
things were wrong and the first render of 4C made both obvious.

### The pink was not the wounds

`POST_HOT_RGB` was `(1.000, 0.160, 0.440)` — saturated magenta — and a pillar
flanking a broken panel keeps that cast **for the rest of the run**, because
"the arena remembers". With 31 breaks on 17964 the late frame therefore carried
up to 62 magenta dots, one beside every break, which is the definition of the
floating marker the brief bans. It was never on the list of damage colours
because it is not a damage state; it was the loudest thing on the screen.

It keeps its job and loses its colour: `(1.000, 0.870, 0.760)`, a pale warm
cast, distinguished from the cool `POST_EDGE_RGB` cap by being warm rather than
by being loud.

### The ramp buys its separation by desaturating, not by rotating

4B satisfied "no damage colour may be mistaken for a team" by pushing the ramp
toward magenta, which buys back the blue channel team orange does not have.
That is how it ended up pink. 4C satisfies the same 0.45 separation the other
way:

| | 4B | 4C | to cyan | to orange |
|:--|:--|:--|---:|---:|
| `CRACK_RGB` | (0.880, 0.100, 0.420) | **(0.760, 0.790, 0.840)** | 0.647 | 0.790 |
| `CRITICAL_RGB` | (1.000, 0.060, 0.300) | **(1.000, 0.820, 0.700)** | 0.913 | 0.635 |
| `FRACTURE_RGB` | (1.000, 0.520, 0.720) | **(1.000, 0.930, 0.870)** | 0.871 | 0.836 |

The physical reading is two-part and the ramp is now that reading: a chipped
material first shows **fresh unweathered surface**, which is not coloured at
all, and only a *critical* panel glows — which is incandescence, warm and
washing out to white. `CRITICAL_RGB` is in team orange's hue family at
saturation 0.30 against orange's 0.87, so it reads as hot and never as a team.
`test_no_arena_colour_is_a_saturated_marker` asserts that **nothing the arena
draws is more saturated than the least saturated team colour**, which is the
rule a future phase cannot buy separation back through.

### The lip is what turned a pit into a hole

A dark notch with a bright hairline in it is still a mark lying on a surface. A
dark notch with a *lit broken edge* is a hole, because that is what a chip in a
lit solid does. So a wound has six parts instead of four: chip, **lip**, crack,
two branches, and a **seam**. The lip is state-independent — a broken edge does
not get hotter, it is just broken — so one shared material serves the arena.

**And the first version of it failed the oldest rule in this renderer.** It was
sized as the chip plus the margin on both axes, which is
`0.68 * 0.30 + 2 * 0.070 = 0.344` against a panel 0.300 thick, so every wound
stuck out past the top and bottom of the band it was supposed to be a hole in
and the lit rim inverted its own read: a plate stuck on a wall rather than a
chip in one. A crack has been held to the canonical silhouette since Phase 4A
by `DAMAGE_CRACK_SPAN`; the lip needed the same rule, has it as
`DAMAGE_RIM_SPAN = 0.92`, and `test_a_wound_never_leaves_its_panel_radially`
recomputes both from the constants.

*(There was a second, duller version of the same mistake: the shared lip
material was lost by a half-applied edit, so the first renders drew the lips
with Godot's default white material. Both were found by looking at a magnified
crop of a rendered frame, which is the only way either could have been found —
neither changes a number anywhere.)*

### Connected, and connected to the ball's own hits

From `critical` upward a **seam** joins consecutive shown wounds along the
chord, so a panel with three wounds shows one fissure system rather than three
separate injuries — which is what "connected crack network" asks for and what
4B's rising *count* of unconnected wounds did not deliver. It invents nothing:
both endpoints are wound offsets and a wound offset is a canonical
`panel_local_offset`, so the network is exactly as tied to where the ball hit
as the wounds are. 28 panel-states on 17964 and 18 on 1176 show one.

### Roughness, sections, and a tint that means something

* **Surface roughness** is the one part of the brief's `damaged` state that no
  added geometry can supply, because it is a property of the whole face rather
  than a shape on it. A panel's material roughness now rises with its canonical
  `fraction` below the first damage state and steps with the ledger above it,
  so a beaten panel stops taking a clean highlight before it has a crack.
* **Fractured** recedes each of the panel's three sub-slabs by a different
  amount, so the section boundaries throw their own edges and the slab reads as
  three pieces that have shifted. Inward only: a fractured panel still never
  occupies a pixel a healthy one did not.
* **The tint.** The brief allows "a tiny local Cyan/Orange stress tint" where
  both teams contributed. `panel_damage_teams` reads it from the canonical
  `team_cumulative` rather than counting anything, and `both` is deliberately
  not "the minority is non-zero" — one glancing hit out of nineteen is not two
  teams wearing a panel down together. The minority has to hold 20% of the
  damage; 29 of 1176's 114 damaged panels qualify, and the tint is 20% of the
  way, on the localised glow only. The panel body, the chip, the lip and the
  cracks are never tinted.

---

## 5. The break, and the sequence it has to read as

`BREAK_FRAGMENT_COUNT` goes from 4 to 5, inside the brief's 3–6, because the 4C
framing draws the outer wall 105 px thick instead of 57 and four chunks left
visible gaps in the slab's own footprint as they went.
`BREAK_STRESS_SECONDS` goes from 0.10 to 0.14 so the crack network's flare is
four frames at 30 fps rather than three — the difference between a wall
visibly straining and a single bright instant. Retraction stays at 0.30 s,
because the passage is the point.

**Seed 1176's final wall is the proof, and it reads.** Rendered at the selected
framing and cropped to the wall
(`docs/validation/.../sequence/seed_1176_final_break.png`):

| t | what the frame shows |
|---:|:--|
| 23.10 | the outer wall, worn, an orange pair working on one panel |
| 23.24 | that panel's crack network flaring — the wall is seen to give |
| 23.27 | **it fails**: white flash, the slab coming apart |
| 23.38 | five chunks leaving, a clear gap where the panel was |
| 23.50 | the shock ring at full size, the gap unmistakable |
| 23.63 | **an orange ball going through the hole** |
| 23.77 | outside the arena, escape flare, `ORANGE ESCAPES!` |

A viewer gets *damaged → fractured → failed → escaped* without being told, in
0.67 s. The flood-through tier the brief calls potentially the best moment
still does not exist and still cannot: every shell rotates, so a broken slot is
a gap sweeping past the population rather than a door. The detection is kept
and a test asserts it stays empty, so a future phase that slows the outer
shells finds out. What fires is the weaker tier — a single ball through a fresh
passage — and on 1176 the second of its two **is the winning escape**.

---

## 6. 17964 against 1176, and why 1176 is the master

Both were rendered at the selected framing: eleven stills each at 1080x1920 and
a 540x960 review clip against the unchanged `open_quartal` master.

| | 17964 | 1176 |
|:--|:--|:--|
| balls / breaks | **18 / 31** | 12 / 20 |
| win | opening, 25.78 s | **break, 23.77 s** |
| camera locks | 5.03 s (19% in) | 12.36 s (52% in) |
| static tail | 20.74 s | 11.41 s |
| measured late/early ink | 0.969 | 0.951 |
| hidden critical subjects | 7 | **0** |
| longest ball hidden by the rail | 3.37 s | **0.70 s** |
| **escapee fully framed during the 0.55 s release** | **0.05 s** | **0.57 s** |
| final wall at the climax | 64 healthy, 2 worn, no hole | 64 healthy, 1 damaged, **1 broken** |

17964 is denser and it wins the event counts, which is exactly the comparison
the brief says not to decide on. Two things decide it instead, and both are
about the payoff:

1. **17964's winner leaves the frame almost immediately.** At 1.200 its escape
   is at x = 1044 px, 36 px from the right edge, and the escapee's run-on is
   fully framed for 0.05 s of the 0.55 s release. 1176's escape is at the
   bottom left and stays framed for all of it. The brief says *do not hide the
   escaping ball*.
2. **1176's climax is the wall failing**, which is the sequence the brief calls
   the most important proof of the destruction design, and 17964 has no such
   moment: it wins through an opening that was always there.

1176 also happens to be the candidate with zero hidden critical subjects and
with half its run at the intimate opening framing rather than a fifth.

**Selected: seed 1176, framing C (1.200).**

---

## 7. The master

`satisfying/multishell_production.py` holds every dial the upload depends on as
one frozen object; `satisfying/multishell_production_cli.py` makes and checks
the files. `deliver` and `archive` are **siblings, not a chain** — both encode
from the same PNG sequence and the same master WAV, so neither carries the
other's generation loss, and `test_the_archive_is_not_derived_from_the_delivery_or_the_other_way`
asserts that as a property of the code rather than as a promise.

    output/category3_two_team_v4a/delivery/category3_test2_seed1176_delivery.mp4

1484 rendered frames at 1080x1920 60 fps, 1555 delivered frames (the last is
cloned to cover the score's decay), H.264 CRF 17 preset slow, yuv420p, AAC
192 kbit/s at 48 kHz stereo, `+faststart`, all metadata stripped. 25.4 MB.
The archive is `..._archive.mkv`, the same picture at CRF 12 with 24-bit PCM,
54.0 MB.

### Every check, off the encoded files

| | |
|:--|:--|
| resolution / fps | 1080x1920, 60.000 fps, yuv420p, 9:16 exact |
| codecs | h264 + aac, 48 000 Hz, 2 channels |
| container A/V drift | **+1.7 ms**, 0.10 of a frame |
| black frames | none anywhere |
| integrated loudness | **−19.17 LUFS** |
| loudness range | 3.93 LU (−21.65 to −17.72) |
| sample peak | −2.50 dBFS |
| true peak | **−2.50 dBTP** |
| clipped samples | **0** |
| limiter | not used; no compression applied |
| mono fold loss | **−0.08 dB**, correlation **0.966**, no band shifts at all |
| phone band | −8.3 dB against the master; 91% of the energy in 300–2000 Hz |
| ending silence peak | 0.0 — true digital silence |

**A/V sync is measured from the delivery MP4 twice, two different ways.** The
container comparison above is one. The stronger one is
`_frame_alignment`: it decodes the MP4 at the frame index each canonical event
falls on and compares that image against the rendered PNG of the same index
*and its neighbours*. A one-frame shift of the picture would leave the drift at
zero and move every event; this finds it.

| event | t | frame | best offset | mean abs error |
|:--|---:|---:|---:|---:|
| clone | 0.545 | 33 | **0** | 1.47/255 |
| damage transition | 0.605 | 36 | **0** | 1.47/255 |
| bounce | 0.605 | 36 | **0** | 1.47/255 |
| break | 0.968 | 58 | **0** | 1.48/255 |
| progression | 17.480 | 1049 | **0** | 1.55/255 |
| final wall break | 23.267 | 1396 | **0** | 1.56/255 |
| winner escape | 23.765 | 1426 | **0** | 1.46/255 |

Zero offset on every class, with the residual being CRF-17 compression noise.
The cue audit adds the audio side: every collision, clone, damage transition,
break, crossing and the escape maps to a cue, the audio is never retimed, video
is never early, and the worst error is 0.9975 frames at 60 fps — 16.6 ms, all
of it frame quantisation, which is bounded by one frame by construction. Mean
0.507 frames; the escape itself is 0.09.

### Identity and hashes

| | |
|:--|:--|
| branch | `category3-two-team-production-v4c` |
| base | `65190b2946e385f1415f970b925818ee70986737` |
| seed | 1176 |
| winner | orange, ball 10, by **break**, 23.765 s |
| simulation config digest | `4a3ab8ba22ae7c54981700823cc5b4eaf147c72fc5ab609a244d9cbaeb6ce572` |
| playback digest | `312617c9151f80be3a4cee1837ca53fd18a01864ddc0b913c223be5251b3f16d` |
| event order digest | `f45a70f752ac0bdbd92af4fa7f93d349b18ee022c5277e5141ae63bdd4010eaa` |
| visual config digest | `e438b716da30f062` |
| audio config fingerprint | `39160c5fec9e3148` (`open_quartal`) |
| production fingerprint | `d798fbecb1be5102` |
| final framing | 1.200 of the frame width |
| camera transition | trigger region 2 at 12.097 s, move 11.957 → 12.357 s |
| static tail | 11.41 s |
| resolution / fps | 1080x1920 / 60 |
| encoder | libx264 CRF 17 preset slow, yuv420p, AAC 192k @ 48 kHz, faststart |

SHA-256:

| artefact | digest |
|:--|:--|
| playback | `43a008d346d15438c79fa2be2c7b73f671d8f8b73795466f80d86229ff816c48` |
| master WAV | `f038a1a9b330572484b28adb40e4e9d4b3ea034cbed8f728ece0075c62c30c0e` |
| delivery MP4 | `183740b52902dd284af03bf75aae045400c9ca52faac18e1239fcb8a15b38fe7` |
| archive MKV | `d9a90ef56afd09db5d7eeb2ce412c6d24cf7af3e7bff96031c10e654c67ba841` |

The master WAV digest is the one Phase 4B recorded for this seed. The audio was
re-rendered, not reused, and came back identical.

---

## 8. The human-view gates, on the encoded file

Every frame below was decoded from the delivery MP4, not from the render.
`docs/validation/.../delivery/delivery_gates_seed1176.png`.

| gate | result |
|:--|:--|
| frame 0 — a two-team race, immediately | **pass.** Two balls, one cyan one orange, 70.6 px across, centred, hook readable above them. Movement from frame 0. |
| first 2 s — the clone mechanic | **pass.** First split at 0.545 s: a second orange ball beside the first with a flash. |
| hook | **pass.** Solid to 1.85 s, gone over 0.55 s, then *hidden* rather than transparent — no ghost survives a grade or a thumbnail. |
| middle — populations visibly grow | **pass.** 2 → 6 by the transition, 12 at the climax. |
| one transition, smooth | **pass.** 11.957 → 12.357 s, 0.40 s, centred, 1.474x. |
| no second zoom, late camera static | **pass.** The framed radius after 12.357 s is constant to 1e-12 sampled every millisecond to the end. |
| late — balls large and readable | **pass.** 47.9 px drawn ball against 33.9 px in 4B. |
| late — the final wall dominates | **pass.** 105.4 px apparent thickness, 7.14x the innermost shell. |
| late — busier, not emptier | **pass.** Late ink 0.564 against 0.593 early; 0.951 of the opening. |
| damage reads as structural | **pass.** Dark chips with lit broken lips, seams joining them, no saturated colour anywhere. |
| the final opening reads as tight | **pass.** 50.7 px gap against a 47.9 px drawn ball — 1.378 collision-ball diameters, and the drawn ball is 94% of the gap. |
| the break | **pass.** Flare, failure, five chunks, clear hole, ball through it. |
| winner obvious | **pass.** `ORANGE ESCAPES!` in the team's own colour, placed at the *top* band because the escapee's swept extent is in the lower one. |
| escape obvious, not hidden | **pass.** The escapee is fully framed for the whole 0.55 s release. |
| no accidental freeze, no black frames, no clipping, no drift | **pass.** See section 7. |

---

## 9. Tests

`tests/test_multishell_visual.py` 198 passed, `tests/test_multishell_av.py`
165 passed, `tests/test_multishell_production.py` 15 passed.

Ten Phase 4B camera and framing tests encoded rules the review overturned and
were rewritten to the 4C contract rather than deleted; each rewrite says in its
docstring what the old assertion was and why it no longer holds. The three
substantive ones: `contained` and `outside_frames == 0` (free at 0.850,
impossible at 1.200 and now replaced by *no ball leaves a moving frame* plus a
bound); `0.80 <= FRONTIER_WIDTH_FRACTION <= 0.90` with `half_width < 0.5`
(replaced by the brief's band and an assertion that the arena is *wider* than
the frame); and `left_margin_px > 0` (now asserted negative, symmetric and
bounded).

New, against the brief's own numbered list:

1. **simulation unchanged** — config digest, schema, constant speed, no
   ball-ball collisions, and ball positions identical at two framings.
2. **race winner unchanged** — team, ball, route, time, population and breaks,
   plus a check that the winning break is a real outer-shell break before the
   escape.
3. **only one camera transition** — in both the visual and the A/V modules.
4. **no zoom back out after the lock** — sampled every millisecond to the end.
5. **no lateral camera movement** — and the crop is symmetric and bounded.
6. **final camera static before the win** — tail > 6 s, and nothing moves
   between the lock and the end of the release.
7. **deterministic framing** — stage for stage with the cache cleared, and
   against a freshly derived document.
8. **event-driven trigger** — the trigger is the first canonical crossing into
   its region, the move opens before it, protection only ever pulls earlier.
9. **canonical ball physics unchanged** — see 1.
10. **damage visuals deterministic** — wound for wound and team read for team
    read, twice.
11. **damage tied to impact positions** — including both ends of every seam.
12. **fragments visual-only** — kept from 4B, plus 3–6 chunks and distinct
    offsets.
13. **winner text avoids the escapee** — kept from 4B, across the whole swept
    release.
14. **A/V sync** — the cue audit, plus the frame-alignment check above.
15. **no clipping** — and no limiter.
16. **production resolution and fps** — asserted on the configuration and
    checked on the encoded file.
17. **delivery config deterministic** — fingerprint stable, and a moved dial
    moves it.
18. **production identity deterministic** — byte-identical across two builds,
    and it refuses to exist if it would describe a framing the renderer does
    not use or a document for another seed.

Plus three that came out of looking at the frames: no arena colour may be more
saturated than a team colour; no part of a wound may leave its panel radially;
and the drawn ball must stay a bigger mark than its own streak at both
framings, because the trail is a world length and raising the fraction
lengthens every streak on screen without a constant changing (40.0 px against a
47.9 px ball at the final framing).

The full Category 3 regression — `test_multiplying_shell`,
`test_multiplying_shell_audio`, `test_multishell_av`, `test_multishell_visual`,
`test_multishell_production`, `test_shell_escape`, `test_tile_escape` and the
five `test_tile_escape_phase*` modules — is **906 passed, 1 skipped, 0 failed**.
`tools/two_team_phase4c_lab.py` joins the named Category 3 exemption in
`test_no_other_category_imports_category_three`.

### The whole repository

`python -m pytest tests` on this branch and on the base SHA, same machine, same
interpreter, randomisation off:

| | passed | failed | skipped |
|:--|---:|---:|---:|
| `65190b2` (Phase 4B) | 6587 | **21** | 441 |
| this branch | 6628 | **21** | 441 |

**The failing node-ID sets are byte-identical.** Not the counts - the sets,
compared with `comm` after sorting, with nothing on either side. All 21 are
pre-existing branch-scope guards belonging to other categories, which compare
the working tree against `main` and therefore fire on any branch that adds
files: `test_this_branch_changed_no_race_fight_or_v30_code` in three Company OS
modules, six `race2` "this branch changes only X" guards and their
`no_locked_file_moved` parametrisations, five `sloped` parallax tests, and
`test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised`,
which fails because Godot *is* installed on this machine.

The +41 passed is this phase's new tests. Nothing was weakened to get there:
the ten rewritten tests each assert a stricter or equally strict property under
the new contract, and three of them assert things 4B could not check at all.

---

## 10. Files

- `satisfying/multishell_visual.py` — the one-transition schedule, the frame
  edge in `critical_visibility_report`, the richer `containment_report`, and
  the seam, team-read and roughness derivations.
- `satisfying/multishell_production.py` — the production identity. New.
- `satisfying/multishell_production_cli.py` — frames, audio, delivery, archive
  and QC. New.
- `godot/scripts/multishell_scene.gd` — the same schedule, the six-part wound,
  the seam, the roughness read, the fracture displacement and the tint.
- `tools/two_team_phase4c_lab.py` — the A/B/C experiment, the uniform occupancy
  measurement, the beat strips and the measurement dump. New.
- `tests/test_multishell_production.py` — the production contract. New.
- `docs/validation/category3_two_team_shell_race_v4c/` — evidence.

**One thing to know before re-running the review pipeline.**
`multishell_av_cli mux` writes its report to the *v4a* validation folder,
which is where Phase 4A and 4B keep theirs, so running it overwrites Phase 4B's
recorded `mux_review.json` with whatever candidates were just muxed. It did
here, and the file was restored from git and the 4C numbers kept separately as
`mux_review_v4c_framing.json`. The path is 4A's and is left alone rather than
moved, because 4A's and 4B's documents both cite it.

---

## 11. Open questions for the human review

1. **The ending is a held card for 1.38 s.** The escape ring finishes at
   24.52 s and the file ends at 25.92 s, so the last 1.38 s is a frozen frame
   carrying `ORANGE ESCAPES!` while the score's final chord decays; the last
   0.15 s of that is the audio design's own end silence. It is not a dead tail
   in the sense of content after the story with nothing happening — the chord
   is still sounding for 0.95 s of it — but it does mean the winner caption is
   up for 2.15 s against the brief's "approximately 0.5–0.8 s or enough for
   readability". Ending the file earlier would cut the escape chord, which the
   brief freezes. Is the held card right, or should the delivery be trimmed to
   the last audible sample?
2. **Late ink is 0.951 of early on 1176, not above it.** The brief's floor
   ("not approximately half") is cleared comfortably and the stretch ("late ≥
   middle") is missed by 1.9%. 17964 meets the stretch and loses the payoff.
   Acceptable?
3. **A ball is partly off frame on 11.6% of 1176's frames**, always at a
   horizontal cap, always after the lock, never a critical subject. That is the
   price of 1.200 and the reason 1.200 is worth it. Is the trade right, or is
   1.100 — which costs 7.5% of every size — the safer master?
4. **The inner shells end as a ring of pale dots.** Once shells 0 and 1 are
   broken through, what survives is their pillars, seen end-on. It is
   structurally honest and it reads as debris now that it is not magenta, but
   it is a distinctive look and worth a decision.
5. **17964 is not gone.** If the denser race is wanted over the destruction
   ending, its master would need the framing dropped to 1.100 or 1.000 to keep
   its escapee on screen through the release. That is one render and one
   encode, not a new phase.
