# V23 — a world for the machine to be in

**Status: built, measured, awaiting review. Not merged.**

V23 is a repaint of V22.1. The race is the same race: same seed, same replay,
same solved camera track, same edit, same cues, same 1592 frames. What changed
is the world the machine stands in and the colours the machine is painted in,
and those are two separate switches that do not reach each other.

    --environment=aurora_valley     the world
    --machine=v23b                  the machine

---

## 1. Purpose

The environment lab's verdict on V22.1 was that its world reads as a test
environment rather than a place: a bright tan sky the machine competes with, a
fork lit white at the one node a marble chooses at, three distant ranges within
about 4 L\* of one another, and twenty-three pieces of atmospheric dressing
sitting below the horizon where no camera has ever seen them. The machine lab's
verdict was that the machine has no zone language — the start, the mixer, the
split and the finish are all much the same cream.

V23 answers both at once, and the answering-at-once is the point: the two labs
measured their subjects against *different* backgrounds, and a dark world under
a brighter machine is a third thing neither of them rendered.

## 2. Source branches

| branch | commit | what it contributed |
| --- | --- | --- |
| `v23-environment-direction` | `b29f6cd` | the art answer: three directions, Aurora recommended. Lab tooling only, no production file touched. |
| `v23-environment-system` | `4af512b` | `EnvironmentProfile`, the JSON registry, the Godot and Python readers, `environment_builder`, `--environment=`. |
| `v23-machine-color-lab` | `5768cea` | `lab_palette.MACHINE_PASSES`, three zone languages, `--machine=`. |

Cherry-picked in that order onto `origin/main` (`e697a12`, the accepted V22.1
production baseline). The first two applied clean; the third conflicted in three
files, resolved semantically — see §10.

## 3. Chosen environment

`aurora_valley`, a delta profile over `alpine_neon`.

## 4. Why Aurora won

The lab's own argument, unchanged: the concept the brief describes — dark
background, glowing machine, cyan/blue/violet high in the frame, orange where
the choice is, gold at the finish, graphite structure over a silver track — is
close to a literal description of Aurora Valley, and the other two directions
each refuse one clause of it on purpose. Collector Canyon refuses the dark
background; Graphite Grid refuses toy-like, and pays for its silhouette with
five backdrops out of eleven that are a featureless wall.

Aurora was also the only direction that improved depth, readability and the
warm-accent story at the same time.

## 5. What was borrowed from Collector Canyon

**Its glow discipline, as a number.** Aurora ran 1.10 / 0.22 / 1.30 in the lab
and clipped 0.80% of its worst frame; Collector ran 0.85 / 0.16 / 1.40 and
clipped 0.69. V23 combines a darker world with a machine that got *brighter* in
three sections, so it takes the lower of the two: `intensity 0.85`, `bloom
0.16`, `hdr_threshold 1.40`.

**Its near-ground value discipline** — but reconciled, because the lab and the
brief pull opposite ways here. The lab said Collector stays legible in the
branch and merge frames where Aurora goes dark, so lift Aurora's ground a step.
The brief said keep the near ground dark and restrained so nothing competes with
the machine. Both are satisfiable as a *compression*: the darkest ground values
come **up** (cliff 14.9 → 17.4 L\*, boulder 15.4 → 17.2) so the landform reads,
and the lightest come **down** (earth 29.9 → 27.4, scree 26.1 → 25.0) so no
hillside competes. The band is 10 L\* wide against Aurora's 15 and Collector's
21, which is also the brief's "lower local contrast near track", and it sits off
black rather than on it. Hue stays Aurora's cool — Collector's warm putty would
have put a warm ground under the orange fork and the gold finish, which is the
one thing the brief explicitly forbids.

## 6. What was borrowed from Graphite Grid

**The crest lines, and nothing else.** Graphite bought silhouette by making the
world near-black and paid with empty voids; the crest lines were the part that
worked without that cost, because they draw the *top edge* of a far mass so a
range reads as a mountain rather than as a darker patch of sky. Nine thin lit
bars at radius 420–560, tilted so they do not read as a row of identical
dashes. No valley grid, no neon floor, no grid world.

## 7. The EnvironmentProfile architecture

Unchanged from `v23-environment-system`, and V23 is its first real customer. A
profile is a JSON file; `extends` gives delta inheritance; a `null` erases an
inherited key; a `contrast` block composes the V21 readability pass on top;
`accent` reaches only profile-owned values. `EnvironmentProfile.validate`
refuses any profile that names a terrain **shape** field, because
**GEOMETRY IS NOT THEME** — a theme may not move the ground the physics runs on.

V23 added five builders to `environment_builder.gd` and two renderer fields.
Every one of them is **off unless a profile asks**, which is what lets the four
shipped profiles keep reproducing their committed frames:

| addition | guard | default |
| --- | --- | --- |
| `backdrop.ridge_range` | no masses | draws nothing |
| `backdrop.crest_lines` | `count` | 0 |
| `backdrop.aurora` | `tiers` | empty |
| `backdrop.mist` | `decks` | 0 |
| `sky.sun_curve` | `has()` | the property is not written at all |
| `grade.ambient_colour` | `has()` | the property is not written at all |

Those last two started out assigning what the documentation says is the engine's
default when a profile is silent. That was not neutral: it moved two of three
V22.1 probe frames. Writing a default you believe to be the engine's is a guess;
not writing the property is not. Both are now `has()`-guarded.

Two new palette surfaces, `haze_vapour` and `lit_crest_line`, are likewise named
by no shipped profile.

## 8. The `aurora_valley` profile

The values that carry the look:

| section | value |
| --- | --- |
| sky | top `#050A1E`, horizon `#1E4C6E`, curve 0.10, sun_angle_max 3.0, sun_curve 0.12 |
| sky ground | bottom `#1B2C40`, horizon `#2B4763`, curve 0.22 |
| grade | background 0.52, exposure 0.81, white 12.0, saturation 1.30, ambient 0.75 at 45% sky over `#3A5C80` |
| fog | `#1D3D5C`, energy 0.60, density 0.0034, aerial 0.92, sky_affect 0.38, sun_scatter **0.04** |
| glow | 0.85 / 0.16 / 1.40 |
| ranges | four cool steps: 11.7 / 17.5 / 22.8 / 27.7 L\*, lifted 16 / 26 / 36 and stretched 1.30 / 1.55 / 1.70 |
| zones | start cyan, mix violet, obstacle amber, **split orange**, merge amber, finish gold |

### Two numbers that did not transfer, and why

**`fog.sun_scatter` is a property of the light rig, not of the look.** The lab
authored Aurora at 0.24 under its own lights. Dropped into production — where
the Key runs at 2.85 — the same number washed the entire upper sky to a
warm-grey mauve, (143,109,113) where the profile asks for near-indigo. It is the
fog taking the colour of the directional lights, and it scales with their
energy. At 0.04 the sky is (24,21,35) and the atmosphere is still there. A
scatter value cannot be carried between rigs; it has to be re-measured.

**A dark sky cannot supply ambient, and no amount of `ambient_energy` fixes
it.** Ambient is sampled from the sky and `ambient_sky_contribution` was 1.0, so
under Aurora's near-black dusk every surface the key did not reach rendered at
zero. This was found the hard way: the massif in front of the mountains was a
flat black hole, and raising ambient fourfold, the world key twofold, the fog
density threefold and the rock albedo threefold **each changed the measured
pixel by nothing at all** — a multiple of nothing is nothing. `ambient_colour`
with a contribution below 1.0 is the floor a dark world needs.

## 9. Machine pass v23b

The lab's balanced signature, taken as shipped: start cyan, mixer violet,
general track silver/light metallic, split orange/amber, finish gold, supports
dark graphite. `v23a` is subtler than the brief asks for and `v23c` trades
marble readability for zone identity; neither ships.

## 10. Machine and environment are separate, and stay separate

This is the architectural rule the integration exists to protect, and the
conflict resolution is where it was decided.

`5768cea` conflicted with the environment system in three files. In none of them
was one side taken whole:

* **`lab_palette.gd` `get_material`** — both override layers kept, ordered
  contrast → machine → environment. Last is *not* "wins": the two tables are
  meant to be disjoint, and a test fails if a shipped pair ever names the same
  key. The fix for an overlap would be to move the key, not to reorder.
* **`course_scene.gd`** — both switches kept, both off by default. They reach
  the palette by different doors: the machine pass is a constructor argument,
  the environment is an override table applied afterwards, so neither can shadow
  the other by accident.
* **`test_sloped_contrast.py`** — the assertion was about the *contrast* gate,
  and both V23 commits had widened the signatures it spelled out. Rewritten to
  assert the gate rather than the argument list, plus that both new switches are
  off by default.

Measured, on the shipped pair: `aurora_valley` names 20 world surfaces, `v23b`
names 25 machine surfaces, **and the intersection is empty**. Neither
`build_environment` nor `build_lights` takes the machine pass.

Two stale assertions from the lab branches were also corrected, both because
they had been true of a lab branch and were not of an integration branch:
`test_the_lab_changed_no_production_file` now scopes to the lab's own commit
rather than to the whole branch, and
`test_no_pass_reaches_the_light_rig_or_the_grade` now asserts that `_machine`
appears in neither world call rather than pinning an exact argument list — the
environment profile is *supposed* to reach the sky.

## 11. Fork treatment

V22.1 lights `split` at `#EAF7FF` — white, the one colour that says nothing, at
the one node on this course a marble chooses at. V23 lights it `#FF9A4E` at
energy 3.2, and the machine's own split gates go orange and blue under `v23b`.

This is the clearest single win at phone size. In V22.1 the orange gate sits
against an orange-brown sky and the route language is nearly invisible; in V23
it sits against a deep blue valley and the choice reads before the marbles
arrive. It also stays away from being a nightclub: warmth is spent in exactly
four zones — obstacle, split, merge, finish — and the start and mixer stay cool.

## 12. Horizon and depth

The three shipped ranges were within about 4 L\* *in the rendered frame*
because the fog converged them. Aurora fixes the cause rather than the symptom:
**aerial perspective converges on the sky, and this sky is dark**, so distant
rock gets darker rather than paler. The four rock values step 11.7 / 17.5 / 22.8
/ 27.7 L\* and the fog is `#1D3D5C` rather than a pale slate, so recession is
visible instead of being a wash.

A fourth layer, `ridge_range`, fills the eighty units between where the near
terrain fades (radius 94) and where the nearest distant mass stands (210).

## 13. Haze banks and dusk slabs — what actually happened

The brief asked that the 14 haze banks and 9 dusk slabs sitting below the
horizon be moved so they contribute. They were moved, measured, and the finding
is more useful than the fix would have been.

**This course's race cameras see very little backdrop, and the reason is
occlusion, not height.** Three separate causes, found by bisection:

1. The near terrain occludes everything below the skyline, so nothing at
   negative Y at any radius is ever seen — that, and not "below the horizon", is
   why the shipped 14 and 9 never appeared.
2. The far range is a 320-unit-tall wall at radius 580–740, so anything beyond
   it is hidden below Y ≈ +170. A dusk band at radius 880 cannot be seen at any
   height a dusk band belongs at.
3. Scale. A bar 2.2 units tall at 600 units away is not a subtle accent, it is
   nothing. The lab's sizes were authored for the lab's radii.

Everything was then re-placed **in front of** the far range and sized to read.
Toggling each feature off and differencing the delivered frames:

| feature | verdict |
| --- | --- |
| gorge mist | **contributes** — 20 411 px on the descent, 9 910 at the route split |
| crest lines, aurora curtains, dusk band, ridge range | present and measurable in the layer-marker test, but **0 changed pixels** on the delivered race frames |
| haze banks | **0 changed pixels at every placement tried**, including ones where a marker-coloured version covered 20–38% of the frame |

So the haze banks are **turned off in `aurora_valley`** (`clouds.count: 0`). They
could be made visible only by bringing them close enough to read as slabs — the
"pale lozenge" the lab warned about — and the brief is explicit that invisible
dressing should not simply be preserved. Atmospheric depth in V23 is carried by
the fog and the four rock values; there is no slab haze in this world because
this course cannot use any.

The crest lines, curtains, dusk band and ridge range are kept: they are cheap,
they are correctly placed now, and they show in the wider preview framings even
though they do not move a pixel in the twelve race moments. That is a weaker
case than the mist's and it is recorded as such in §20.

### The gorge mist put its slab edges in the sky, and that had to be fixed

At the first placement (`top -28`, `step 10`, `offset 38`, `reach 30` — close to
the lab's own) the mist decks read as two hard-edged grey diagonal wedges in the
upper-left sky of the route-split frame. They are wide, unshaded, depth-write-off
planes, and from a camera that looks across the gorge rather than down into it
they cleared the terrain silhouette and became sky.

This was nearly shipped. It was found by looking at a delivered pair at full
size, not by any measurement — no threshold in the QC suite catches "a soft grey
wedge in the sky", and the frame's numbers were all healthy.

Lowered and pulled in (`top -44`, `step 12`, `offset 30`, `reach 26`) the sky
artefact measures **0 pixels** while the mist still contributes 9 910 in the
gorge where it belongs. That is the shipped setting.

## 14. Clipping and bloom

Re-measured from scratch on the combined frames, as the brief requires, because
the two passes' effects do not add.

| | V22.1 | V23 |
| --- | ---: | ---: |
| world L\* (mean of 16) | 23.46 | **11.40** |
| machine L\* | 89.54 | 86.82 |
| machine/world headroom | 66.08 | **75.41** |
| marble dE (median, race) | 67.76 | **74.48** |
| marble dL | 12.38 | **14.51** |
| worst-frame flat white | 0.027% | 0.144% |

Headroom improves at **every one of the sixteen moments**. The four sections the
labs flagged:

| | clip % | p98 L\* | marble dE |
| --- | --- | --- | --- |
| obstacle | 0.024 → 0.062 | 93.3 → 93.4 | 46.3 → 49.4 |
| branches | 0.020 → **0.144** | 94.1 → 95.3 | 68.5 → 75.4 |
| merge | 0.001 → 0.002 | 92.9 → 94.1 | 107.5 → 113.9 |
| finish | 0.005 → 0.018 | 94.7 → 96.2 | 21.4 → 24.5 |

Branches is the worst frame in the film at 0.144% flat white. That is a sevenfold
relative rise and a negligible absolute one: the V21 readability pass exists
because V20 ran **5.5%** of every frame flat, and 0.144% is thirty-eight times
under it. No threshold was weakened to get there; the glow came down to
Collector's numbers before anything else was considered.

## 15. Phone readability

Reviewed at 270×480 — `docs/validation/sloped_race_v1/v23_integration/phone_sheet.png`.

* **Marble separation** — better, not worse, and measured by projection rather
  than by eye: +9.8% dE, +17% lightness step.
* **Track silhouette** — a light track on a dark cool ground separates further
  than a light track on warm tan.
* **Fork** — the clearest improvement in the film at this size.
* **Zone colours** — start cyan, mixer violet, fork orange and blue, finish gold
  are all distinguishable at 270 px wide, which they were not in V22.1.
* **Obstacle** — the amber obstacle reads against a cool ground.
* **Finish** — gold on near-black instead of gold on tan.

### A metric that was wrong, and how it was caught

The first version of this measurement took the top saturation percentile as
"the racers" and reported that marble separation had **halved**. It had not: on
a V23 frame the most saturated pixels are the machine's own zone lights — the
orange fork and the violet mixer are more saturated than a marble — so the
metric was measuring the machine against itself. The replay and the camera track
already know exactly where every racer is on every frame. The projected measure,
borrowed unchanged from the machine lab, says separation improved at 11 of 12
race moments.

## 16. Metrics

`docs/validation/sloped_race_v1/v23_integration/measures.json`, sixteen moments,
both editions, measured on the finished masters.

No layering score was invented. The environment lab rejected three attempts at
one and that verdict stands: **whether the world has depth is shown, not
scored** — the per-feature visibility table in §13 is a fact about what is drawn,
not a quality metric, and the depth claim itself rests on the frames.

## 17. Comparison with V22.1

Sixteen exact same-frame pairs. Because V23 renders V22.1's own track over
V22.1's own replay to V22.1's own edit, the two films share a clock exactly and
a pair is frame *n* beside frame *n* — any difference in what the marbles are
doing would be a bug.

`pair_*.png`, `contact_sheet.png`, `phone_sheet.png` in
`docs/validation/sloped_race_v1/v23_integration/`.

## 18. Tests

`tests/test_sloped_v23_integration.py` — 33 tests: profile registration and
validation, delta inheritance, shape-field rejection (asserted *and* enforced),
environment/machine surface disjointness, the palette's layer order, neither
switch reaching the other, edition gating, no older edition gaining a V23 flag,
the two strings written once, V23 reusing V22.1's own track files, shared edit
and cue policy, no output path collision, the seed, the builders being off by
default, the shipped profiles asking for no V23 feature, the fork no longer
white, warmth confined to four zones, Collector's glow discipline, the four
separated rock steps, the compressed ground band, and the V21 overlay composing
without overwriting what Aurora authored.

All three source suites pass unchanged apart from the two stale assertions
described in §10.

### V22.1 backward compatibility, proved rather than asserted

Three stills — the start grid, the descent and the branches — rendered from this
branch with no `--environment` and no `--machine`, against the same three
rendered before any V23 code existed:

    at_001.000  BYTE-IDENTICAL
    at_007.000  BYTE-IDENTICAL
    at_016.000  BYTE-IDENTICAL

**The first attempt at this check was itself wrong**, and it is worth recording
how. It reported two of three frames differing, one of them by 306 388 pixels —
because the "before" render had been given `--start-contract` and the "after"
render had not, so the thirty kinematic start parts were in different poses. The
renderer is deterministic: two runs of the same command differ by zero pixels on
all three frames. The lesson is the one this project keeps relearning — check
the instrument before believing a regression.

## 19. QC

`tools/sloped_short.py --edition v23 --stage qc` — every check passes, no
threshold re-baselined:

* 1080×1920, 60 fps, **1592 frames = 26.5333 s**, inside the 26.0–27.0 band
* true peak −1.80 dBTP, integrated −13.97 LUFS
* the winner's crossing is the loudest crossing and the loudest moment
* no black frames (darkest 55.5 luma)
* mpdecimate keeps 1566 of 1592
* overlay timings unchanged

## 20. Weaknesses

1. **Four of the six world features do not move a pixel in the race.** Crest
   lines, aurora curtains, the dusk band and `ridge_range` are correctly placed
   and measurable in isolation, but they change nothing in the twelve race
   moments. They are kept because they are cheap and they do show in the wider
   preview framings — but if a reviewer decides the complexity is not worth it,
   deleting all four from the profile costs nothing and changes no delivered
   race frame. The haze banks were already removed on exactly this reasoning.
2. **This course cannot use slab haze at all** (§13). That is a limitation of
   the course, not of the profile, but it means "atmospheric layering" here is
   fog and rock values rather than anything built.
3. **The near ground is a fairly saturated blue in the wide shots.** It does not
   compete with the machine on value, but it is more colourful than
   "restrained" and is the most likely thing a reviewer will want dialled back.
4. **Branches clipping rose sevenfold in relative terms** (§14) — 0.020% to
   0.144%. Absolutely negligible against the 5.5% the V21 pass exists to have
   removed, but it is the one metric that moved the wrong way.
5. **Landmarks were not added** (brief Part I, optional). Given how little
   backdrop these cameras see, a landmark would have to be large and close, and
   that is a bigger change than a repaint should make.
6. **The gorge mist is the only world feature carrying the depth claim in the
   race**, and it took two attempts to place (§13). It is worth a careful look
   in motion rather than in stills.

## 21. Recommendation

**Ship V23 as the visual edition, subject to watching the film.**

It does what the brief asked: the world reads as a dark stylised valley rather
than a test environment, the machine is the hero in every one of the sixteen
measured moments, the fork finally communicates the route choice, the gold
finish is a payoff instead of gold on tan, and the marbles are measurably easier
to track — at phone size, which is the size that counts.

It does not change the race. Same seed, same replay, same camera track, same
edit, same 1592 frames, same audio structure. V22.1 remains reproducible and
nothing V23 adds is a default.

The open questions are all about taste, not correctness: the near-ground
saturation, whether the subtle backdrop accents are worth their complexity, and
the diagonal band in the route-split sky.
