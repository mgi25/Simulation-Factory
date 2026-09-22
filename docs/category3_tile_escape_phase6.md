# Category 3, Test #1 — HIT EVERY TILE TO ESCAPE — Phase 6: final polish and the production master

**Decision: PRODUCTION MASTER APPROVED.**

The upload is `output/category3_v6/master/category3_test1_seed3530_shorts.mp4`
— 1080×1920, 30 fps, 1,040 frames, 34.667 s, H.264 CRF 17 with 192 kbps AAC at
48 kHz. It passes frame-accurate QC on the encoded file, its audio does not
clip and never asked the limiter for anything, the Shorts safe area is clear at
every moment a viewer is hunting a tile, and the audio and video are
synchronised to **exactly zero**.

Phase 6 was meant to be polish and delivery. It found three real defects, and
the most important of them was in an instrument rather than in the work.

**The defect Phase 5 handed to Phase 6 did not exist, and the fix prescribed
for it could not have worked.** Phase 5 reported that on the densest
pacing-valid seed nine activations in fifty failed to clear 3 dB above the bed
under them, and recommended ducking the duplicate bed around each activation.
Phase 6 built the duck, and then measured what was actually in that bed before
turning it on. **Across 250 activations on five seeds, not one has a duplicate
inside the 55 ms window the reading uses.** The duplicate share of the bed's
energy under every one of those nine activations is 0.000; deleting every
duplicate from the mix moves the worst reading by 0.10 dB; and swept from 0 to
0.55 the duck changes the nine-of-fifty count not at all and the
fifth-percentile emergence by 0.03 dB. What sits under an activation is the
*tail of the activations before it* — a 620 ms cue at four to six contacts a
second — and ducking that is both forbidden by the brief and wrong on its own
terms, because a previous activation is also progress. Measured in each
activation's own third-octave band, which is how masking in the ear actually
works, all nine emerge by +3.3 to +73.6 dB. The number that needed to move was
the instrument's.

**Nine of the fifty-one tiles were underneath YouTube's own UI, and one of them
mattered.** A 0.86-wide centred arena puts the right side of the ring beneath
the Shorts action rail. On seed 3530 one of those tiles — tile 11 — is the
**forty-ninth** tile to activate, so through the whole 48/51 window one of the
three remaining dark tiles was behind an icon, and the counter and the picture
disagreed about how much was left. The counter had its own version of the same
problem: its glyphs sat at 0.836–0.878 of the frame height and YouTube's title
and @handle block begins at 0.84.

**A fully retracted gate tile was shrunk, not hidden.** Fourteen lit
sub-pixel slabs stayed on screen from the settled beat to the last frame of the
video. Emission reaching zero is not the same as the object being gone.

All three are fixed. Nothing else in the locked system was touched.

---

## 1. Base and git

| | |
|---|---|
| starting branch | `category3-tile-escape-v5` |
| starting SHA | `997c16134c4bc7e0a974ce2878631f71497a2856` |
| this branch | `category3-tile-escape-v6` |
| worktree | `../wt-category3-tile-escape` |
| Godot | 4.7.2 stable, `$GODOT_BIN` |

The Phase 5 tree was clean at `997c161` and Phase 6 branched from it directly.
Nothing was merged and no history was rewritten.

---

## 2. Part 1 — the activation duck, and the instrument that replaced it

### 2.1 What was measured before anything was built

Phase 5's `masking_report` compares broadband energy in a 55 ms window at a
cue's peak against broadband energy in the 55 ms window immediately before the
event. Phase 6's first action was to decompose that denominator: the same
schedule was rendered three times — everything, duplicates only, and
non-duplicate events only — and the bed window was measured in each.

Seed 37169, the densest pacing-valid seed, the nine activations Phase 5
reported:

| n | t | broadband emergence | bed, full mix | bed, duplicates only | duplicate share of bed energy |
|---|---|---|---|---|---|
| 6 | 1.067 | +2.53 dB | −18.68 dBFS | **−240 dBFS** | 0.000 |
| 7 | 1.200 | +2.96 | −19.62 | **−240** | 0.000 |
| 8 | 1.267 | +1.93 | −16.90 | **−240** | 0.000 |
| 9 | 1.333 | **+0.20** | −14.98 | **−240** | 0.000 |
| 10 | 1.467 | +1.60 | −17.95 | **−240** | 0.000 |
| 12 | 1.767 | +2.68 | −19.44 | **−240** | 0.000 |
| 24 | 5.700 | +2.04 | −17.29 | **−240** | 0.000 |
| 25 | 5.767 | +0.65 | −15.74 | **−240** | 0.000 |
| 38 | 12.567 | +0.80 | −17.69 | −41.54 | 0.004 |

−240 dBFS is the measurement's zero: **there is no duplicate in the window at
all** for eight of the nine, and the ninth contributes four thousandths of the
bed's energy. Deleting every duplicate from the mix raises the worst of the
nine by 0.10 dB and leaves all nine under 3 dB.

That is not a property of the dense seed. Across all five seeds:

| seed | activations with a duplicate placed inside the 55 ms window | within 150 ms |
|---|---|---|
| 3530 | **0** of 50 | 1 |
| 26267 | **0** of 50 | 0 |
| 37169 | **0** of 50 | 9 |
| 6132 | 1 of 50 | 5 |
| 7541 | **0** of 50 | 2 |

The reason is arithmetic that was already in Phase 5's report and had not been
put together: a duplicate cue is 110 ms long, an activation cue is 620 ms, the
median gap between contacts is 200 ms, and events are quantised to 33 ms
frames. The bed under an activation is therefore almost always the decaying
tail of earlier *activations*.

### 2.2 The duck, built to the brief, swept, and measured

`AudioConfig` gained `activation_duck`, `activation_duck_lead_seconds` (0.080),
`activation_duck_tail_seconds` (0.140) and `activation_duck_depth`, and
`tile_score.activation_duck_scale_for` applies it. It meets every requirement
the brief set:

* **duplicates only** — `activation_duck_scale` is 1.0 on every other kind by
  construction, and a test asserts it on a schedule built at depth 0.5;
* **not the activation** — the duck is driven by the event list, so it cannot
  act on the event it is protecting; a test turns it to 0.9 and asserts that
  not one activation, final, unlock, escape or confirm event moves;
* **not a compressor** — no signal detector anywhere; it resolves to one
  scalar per cue, applied before placement;
* **no pumping** — structurally unavailable, for the same reason: there is no
  moving gain inside any sounding voice at any point in the chain;
* **shaped, not switched** — full at the activation's instant, tapering
  linearly to zero at both edges, so consecutive duplicates step by a fraction
  of a decibel;
* **duplicates never disappear** — the depth is bounded below 1.0 at
  construction, and at the configured 0.32 the quietest a duplicate can become
  is 0.68 of what the two existing dampers already left it;
* **simulation timing untouched** — computed on canonical times, like the
  density duck, so it does not move when the frame grid does.

Swept on the production seed and on the densest secondary seed:

**Seed 3530**

| depth | duplicates touched | worst duplicate | broadband masked | broadband p05 | band masked | phone broadband masked | new>dup |
|---|---|---|---|---|---|---|---|
| 0.00 (off) | 0 of 107 | — | 0/50 | +5.12 dB | 0/50 | 5/50 | +12.46 dB |
| 0.16 | 1 | −0.06 dB | 0/50 | +5.12 | 0/50 | 5/50 | +12.46 |
| 0.32 | 1 | −0.11 dB | 0/50 | +5.12 | 0/50 | 5/50 | +12.46 |
| 0.55 | 1 | −0.19 dB | 0/50 | +5.12 | 0/50 | 5/50 | +12.46 |

**Seed 37169, the densest**

| depth | duplicates touched | worst duplicate | broadband masked | broadband p05 | band masked | phone broadband masked | new>dup |
|---|---|---|---|---|---|---|---|
| 0.00 (off) | 0 of 143 | — | **9**/50 | +1.16 dB | 0/50 | 11/50 | +12.57 dB |
| 0.16 | 12 | −1.43 dB | **9**/50 | +1.17 | 0/50 | 11/50 | +12.57 |
| 0.32 | 12 | −3.14 dB | **9**/50 | +1.18 | 0/50 | 11/50 | +12.57 |
| 0.40 | 12 | −4.14 dB | **9**/50 | +1.18 | 0/50 | 11/50 | +12.57 |
| 0.55 | 12 | −6.40 dB | **9**/50 | +1.19 | 0/50 | 11/50 | +12.57 |

A 6.4 dB duck on twelve duplicates moves the defect metric by **0.03 dB** and
fixes **zero** events. On the production seed it touches one duplicate of 107
by a tenth of a decibel.

The brief asked for "the smallest reduction necessary to make progress hits
consistently perceptible". Measured, that reduction is **zero**, and that is
what ships: `activation_duck = False` in every configuration, with the
mechanism present, tested and one field away. The comment on the field carries
the measurement, so anyone turning it on has to bring a new one.

### 2.3 `band_masking_report` — the right instrument

`satisfying/tile_audio.py` gained a second masking instrument that asks the
same question inside each event's own **third-octave band** — the width a
standard analyser uses, and close enough to a critical band over 220–880 Hz to
be the right width rather than a chosen one. It is a Goertzel over the DFT bins
in the band, Hann-windowed, in pure Python so it stays inside the same chain
that renders the samples.

It was checked against something independent before its numbers were believed:
against numpy's transform on eighteen signals it agrees to **0.000000 dB**, and
it rejects a tone a fifth away from the band centre by 59 to 82 dB. Both are
tests.

Seed 37169's nine, in their own bands:

| n | f0 | broadband | own band |
|---|---|---|---|
| 6 | 523.3 Hz | +2.53 dB | **+34.77 dB** |
| 7 | 261.6 | +2.96 | +25.50 |
| 8 | 220.0 | +1.93 | +16.31 |
| 9 | 261.6 | +0.20 | **+3.27** |
| 10 | 523.3 | +1.60 | +10.67 |
| 12 | 329.6 | +2.68 | +46.28 |
| 24 | 440.0 | +2.04 | +11.75 |
| 25 | 587.3 | +0.65 | +8.27 |
| 38 | 440.0 | +0.80 | +73.59 |

Across all five seeds, both instruments, master and phone:

| seed | broadband masked, master | broadband masked, phone | **band masked, master** | **band masked, phone** | band median, master | band min, master | band min, phone |
|---|---|---|---|---|---|---|---|
| 3530 | 0/50 | 5/50 | **0** | **0** | +48.4 dB | +8.44 dB | +8.09 dB |
| 26267 | 0/50 | 10/50 | **0** | **0** | +49.2 | +6.68 | +5.57 |
| 37169 | 9/50 | 11/50 | **0** | **0** | +46.3 | +3.27 | +4.01 |
| 6132 | 1/50 | 8/50 | **1** | **1** | +64.7 | **+0.91** | **+0.91** |
| 7541 | 1/50 | 8/50 | **0** | **0** | +47.8 | +7.41 | +6.37 |

**The one genuine case in 250.** Seed 6132's activation 8 emerges by +0.91 dB,
and seed 37169's activation 9 by +3.27 dB, and both have the same cause: two
tiles that **share a fundamental** activating within 200 ms, so the second
really does arrive inside the first's still-ringing channel. Neither
neighbourhood contains a single duplicate.

| seed | first | second | gap | pitch |
|---|---|---|---|---|
| 6132 | tile 36 at 1.400 s | tile 18 at 1.600 s | 200 ms | both 587.3 Hz |
| 37169 | tile 47 at 1.200 s | tile 6 at 1.333 s | 133 ms | both 261.6 Hz |

This is a property of a seed, not of the mix. Four tiles share each of the
eleven notes, so whether a run contains the collision is decided by the order
the ball happens to find them in. **Seed 3530 contains none**, its worst
activation clears by +8.44 dB on the master and +8.09 dB through a phone, and
it is the seed being shipped. Left open rather than fixed: fixing it would mean
either widening the vocabulary, which Phase 5 argued against for good reasons,
or re-pitching a tile by collision order, which would break the property that a
tile's note is a function of where it is and nothing else.

---

## 3. Part 2 — the hook decision

One controlled comparison, at both sizes, with one variable. Same seed, same
playback document, same renderer, same frames; only the hook line differs.

| | **A** `HIT EVERY TILE TO ESCAPE` | **B** `CAN IT HIT ALL 51?` |
|---|---|---|
| characters | 24 | 18 |
| cap height, 1080×1920 | 43 px | 43 px |
| cap height, 270×480 | 10 px | 10 px |
| contrast against the band behind it | +232 levels | +232 levels |
| box width, 1080×1920 | 717 px — 66.4% of the frame | 515 px — 47.7% |
| ink | 10,627 px — 0.512% of the frame | 6,752 px — 0.326% |
| safe area, all three models | CLEAR | CLEAR |
| gap to the counter | 0.657 of the frame height | identical |

**First-frame readability is identical and measured so.** Both lines are drawn
at the same font size, so cap height and contrast are the same number; neither
is easier to read than the other.

**B's only measurable advantage is footprint** — 36% less ink. That advantage
buys nothing, because A's 0.512% of the frame already clears every safe-area
model with room, so nothing was constrained by it.

**A wins comprehension.** A states the goal *and the stake*: hit every tile,
**to escape**. B states the goal and drops the stake. The entire climax —
detonation, confirmation hold, gate unlock, escape — is 2.48 s of payoff whose
meaning is "it got out", and a viewer who was never told escape was the point
has no frame for it.

**A wins its relationship with the counter.** The counter reads `X / 51` from
frame 0. B's "51" duplicates the denominator the counter already supplies, and
spends the line's only number saying something the screen is already saying. A
carries no number, so the two lines reinforce rather than repeat.

**Curiosity is the one place B has an argument** — an interrogative invites a
yes/no bet where a statement sets rules — and it is not measurable here, so it
is recorded as an argument and not as a result.

One measured advantage to B that relieves no constraint, one unmeasured
argument for B, two arguments for A. There is no clearly stronger result, so by
the brief's own rule the hook is **retained**:

> **HIT EVERY TILE TO ESCAPE**

No further hook variants were made. The choice is pinned by a test, in the
production config and in the scene's own `HOOK_DEFAULT`.

---

## 4. Part 3 — the Shorts safe area

### 4.1 The model

`satisfying/tile_safe_area.py` is new. Its regions are derived in
device-independent pixels on a 412 dp viewport and expressed as fractions, so
they hold at any render size. Three of them:

| model | action rail | what it is for |
|---|---|---|
| `shorts_measured` | x 0.859–0.976, y 0.440–0.910 | the strip as it measures on a screenshot, no margin — says how much of a reading is the real UI |
| **`shorts_conservative`** | **x 0.840–1.000, y 0.420–0.930** | **the gate**: the real strip plus 20 dp of margin on the left |
| `shorts_strict` | x 0.810–1.000, y 0.380–0.940 | a stress test, 30 dp wider again — says how much further the player could grow |

Only `shorts_conservative` is a gate. Reporting a deliberately over-drawn
stress model as a failure would make caution look like a defect, so the other
two are printed as margin readings.

"Covered" is measured two different ways because it is two different questions.
**Tiles are geometry**: each one's drawn face is a known quadrilateral, so the
fraction inside a region is exact and needs no render. **Type is pixels**: the
hook and the counter are placed by Godot's font metrics, so their boxes are
read back out of a rendered frame. The ball is geometry over time, sampled on
the frame grid.

### 4.2 What the old composition did

Seed 3530, arena 0.86 wide and centred — the Phase 3–5 composition:

| model | tiles obstructed (≥25% covered) | worst tile | late-game tiles obstructed | ball hidden, longest |
|---|---|---|---|---|
| `shorts_measured` | 7 of 51 — tiles 9–15 | #10 at **100%** | **tile 11** | 0.033 s |
| `shorts_conservative` | 9 of 51 — tiles 8–16 | #9 at **100%** | **tile 11** | 0.067 s |
| `shorts_strict` | 11 of 51 — tiles 8–18 | #9 at **100%** | **tile 11** | 0.100 s |

Seed 3530's last four tiles to light are 20, **11**, 30, 50. Tile 11 is the
**forty-ninth**, and it is 100% covered on every model. So for the whole 48→49
window — which the Phase 4 pacing gate allows up to 4.5 s — the counter said
three tiles remained and the viewer could see two.

And the counter, measured on a real frame rather than predicted:

| | box, fraction of height | `shorts_measured` | `shorts_conservative` | `shorts_strict` |
|---|---|---|---|---|
| hook | 0.0854–0.1073 | CLEAR | CLEAR | CLEAR |
| **counter** | **0.8359–0.8771** | **53.6% inside the title block** | **90.1% inside** | **100% inside** |

### 4.3 The adjustment

The brief asked to prefer a very small scale or position adjustment. The rail is
on the right and only on the right, so the cheapest fix is to stop treating the
frame as symmetric:

| | before | after |
|---|---|---|
| `ARENA_WIDTH_FRACTION` | 0.86 | **0.765** |
| `ARENA_CENTRE_OFFSET_FRACTION` | — (centred) | **−0.060** |
| `COUNTER_TOP_FRACTION` | 0.815 | **0.745** |

A centred shrink would have had to reach **0.68** to clear the same rail, which
costs 21% of scale; the offset buys half of that back for 11%. The arena now
spans x 62.1–888.3 px (5.75%–82.25% of the frame) with the rail at 907.2 px —
**18.9 px of clearance** and a 5.75% left margin.

The camera converts the offset with its own `size`, so it is resolution
independent: `camera_x = −offset × camera.size`. `tile_readability.project`
adds the same offset, which keeps it a pure scale *plus a translation* — and a
translation cancels in any difference of two projected points, which is why
every Phase 3 distance measurement survives unchanged.

`tile_completion` needed the offset too. It decides when the ball has left the
frame, and the frame moved; an escape computed against a centred frame would
cut the ball off on one side and leave it hanging on the other. Its
`frame_half_width_wu` went from 11.63 to 13.07 world units, the escape from
0.446 s to 0.476 s, and the climax from 2.412 s to **2.479 s**. The run itself
is untouched — see §8.

### 4.4 What the new composition does

Every model, every pacing-valid seed:

| model | obstructed | worst dark-tile cover | final tile | ball hidden |
|---|---|---|---|---|
| `shorts_measured` | **0** of 51 | **0.000** | 0.000 | **0.000 s** |
| **`shorts_conservative`** | **0** of 51 | **0.104** | 0.000 | **0.000 s** |
| `shorts_strict` | 6 of 51 | 1.000 | 0.000 | 0.000 s |

`shorts_strict` still shows exposure, which is what a stress model is for: it
says the player's rail could grow another 30 dp before this composition would
have to move again. It is not the gate, and the final tile is clear even there.

At every moment the brief names, on the production seed, with the conservative
model:

| moment | frame | lit | dark remaining | worst cover of a dark tile |
|---|---|---|---|---|
| opening | 0 | 0 | 51 | 0.104 |
| 48/51 | 732 | 48 | 3 | **0.000 — all clear** |
| 49/51 | 806 | 49 | 2 | **0.000** |
| 50/51 | 865 | 50 | 1 | **0.000** |
| final hit | 964 | 51 | 0 | — |
| confirming | 968 | 51 | 0 | — |
| unlocking | 983 | 51 | 0 | — |
| escaping | 992 | 51 | 0 | — |
| settled | 1024 | 51 | 0 | — |

And the type, measured on frame 300 of the real render: hook 0.1685–0.8315 ×
0.0854–0.1073 **CLEAR**; counter 0.3398–0.6435 × **0.7651–0.8068 CLEAR** of
every model, including the strict one whose title block starts at 0.815.

Overlay proofs for all nine moments are in `output/category3_v6/safe_area/`,
as `<moment>_shorts_conservative.png` beside `<moment>_plain.png`.

### 4.5 Readability after the change

The brief asked for mobile readability to be revalidated if the composition
moved.

| | 0.860, centred | **0.765, offset** | 0.680, centred |
|---|---|---|---|
| scale | 46.44 px/wu | **41.31** | 36.72 |
| ball, collision / drawn | 41.8 / 60.6 px | **37.2 / 53.9** | 33.0 / 47.9 |
| tile, drawn length | 48.4 px | **43.0** | 38.2 |
| travel per frame at 30 fps | 131.6 px | **117.0** | 104.0 |
| trail length | 355.3 px | **316.0** | 280.9 |
| `trail_covers_frame_step` | True | **True** | True |
| trail / worst frame step | 2.70× | **2.70×** | 2.70× |
| trail sample spacing | 0.345 ball radii | **0.345** | 0.345 |

The strobe verdict is **scale invariant**: the trail is a time window and the
frame step is a time window, so both scale together and their ratio is a
property of speed and frame rate rather than of composition. That is why an 11%
shrink costs nothing Phase 3 established.

At 270×480 — the repository's phone check — with the new composition:

| moment | lit | worst tile gap | Michelson | single dark tile findable | hook | counter |
|---|---|---|---|---|---|---|
| early 8/51 | 10 | 127.9 | 0.489 | — | 10 px, clear | 19 px, clear |
| mid 26/51 | 26 | 129.8 | 0.499 | — | 10 px, clear | 19 px, clear |
| late 49/51 | 49 | 129.3 | 0.494 | — | 10 px, clear | 19 px, clear |
| **late 50/51** | 50 | **140.3** | **0.562** | **True** | 10 px, clear | 19 px, clear |

---

## 5. Part 4 — final visual polish

Restraint was the instruction and restraint is what happened: **one change**,
and it fixes a defect rather than adjusting a taste. Everything else on the
brief's list was measured, found healthy, and left alone.

### 5.1 The one change: the gate leaves nothing behind

At full retraction the scene computed `shrink = maxf(0.02, 1.0 - e)` and
dropped the tile's emission to zero — but never hid the node. A tile at 2% of
its size is still **0.86 px** of albedo lit by the scene's own lights, and there
are fourteen gate tiles:

| frame | isolated bright pixels on the gate's arc, before | after |
|---|---|---|
| 983 (unlocking) | 0 | 0 |
| 1000 | **14** | **0** |
| 1010 | **11** | **0** |
| 1024 (settled) | **14** | **0** |
| 1039 (last) | **14** | **0** |

They measured up to 84 of 255 against a background of 8, sat symmetrically
about the arena's centre, and stayed there for the last half-second of the
video. `GATE_RETRACT_MIN_SCALE` is now a named constant and visibility is tied
to it, so the tile disappears at exactly the instant it would otherwise stop
shrinking — at which point it is already under a pixel wide with 2% of its
energy, so the animation is unchanged and only the leftovers are gone. The
`else` branch restores visibility explicitly, because the function runs fresh
every frame and remembers nothing, which is also what makes a single still of
any instant correct.

### 5.2 What was reviewed and left alone

| item | measurement | verdict |
|---|---|---|
| inactive tile contrast | median 54–57 of 255 | left |
| active tile brightness | median 206–207 | left |
| population separation | gap 138–151, ratio 3.6–3.8×, Michelson 0.51–0.58 | left |
| single dark tile at 50/51 | `single_remaining_tile_identifiable` **True**, worst gap 150.8 | left |
| newly activated flash | +193 bright px over the frames before it | left |
| final-tile flash hierarchy | +367 px — **1.90×** an activation, correct order | left |
| duplicate response | +2 px — essentially nothing, which is the design | left |
| ball halo and 0.09 s trail | trail 316 px against a 117 px frame step, 2.70× | left |
| bloom / climax brightness | fully-white pixels: 0.18% at the detonation, 0.59% at the unlock, **0%** at settled | left |
| confirmation pulse | 2.57% of pixels above 200; a localised core, not a blown frame | left |
| text alignment | hook and counter centred, both clear of every UI model | left |
| counter hierarchy | white during play → amber at 50/51 → orange at 51/51 | left |

The visual and audio hierarchies were re-checked together, as Phase 5's
recommendation 4 asked. Visual: duplicate ≈ 0 px < activation +193 px < final
+367 px. Audio: duplicate 0.098 < activation 0.300 < final 0.760. Both in the
right order, and the final-over-activation ratios are 1.90× visually and 2.53×
in gain.

---

## 6. Part 5 and Part 6 — the final audio master, mono and phone

Baseline: the selected **drone** confirmation hold. `DEFAULT_CONFIG` moved to
`v3_hold_drone`, which is the one-line change Phase 5 said it would be.
Deliberately *not* a fifth `CONFIGS` entry called "production": a new entry that
sounded exactly like `v3_hold_drone` would give the registry two names for one
sound, and the test that four configurations produce four distinct waveforms is
worth more than a nicer label.

### 6.1 Levels, clipping and limiter

| | requirement | measured, PCM master | measured, decoded from the MP4 |
|---|---|---|---|
| sample peak | ≤ −1.3 dBFS | **−1.83** | −1.754 |
| true peak | ≤ −1.0 dBTP | **−1.49** | **−1.587** |
| clipped samples | 0 | **0** | **0** |
| samples over the ceiling | 0 | **0** | — |
| limiter gain reduction | — | **0.00 dB, never engaged** | — |
| integrated loudness | — | −18.87 LUFS | −18.89 LUFS |

The limiter not acting is what makes "an event's peak in the mix is its
configured gain" true rather than nearly true. The encoded true peak is
**0.1 dB quieter** than the PCM master's, so the 0.3 dB reserve Phase 5
measured for AAC overshoot was never called on.

### 6.2 The hierarchy, in three listening conditions

| | master | mono fold | phone (500 Hz high-pass, mono) |
|---|---|---|---|
| duplicate, median peak | −20.57 dBFS | −21.77 | −27.12 |
| activation, median peak | −8.11 | −9.69 | −12.17 |
| final hit, peak | −1.83 | −2.55 | −3.94 |
| **activation over duplicate** | **+12.46 dB** | **+12.08** | **+14.95** |
| **final over activation** | **+6.28 dB** | **+7.14** | **+8.23** |
| unlock / escape | −2.17 | −2.18 | −5.49 |

Everything that carries meaning is *louder* relative to the bed on a phone than
on the master, which is Phase 5's correction still holding. The mono fold
narrows the new-over-duplicate gap by 0.38 dB and *widens* final-over-activation
by 0.86 dB.

### 6.3 Does the panning cost anything in mono?

Asked properly, which the first attempt did not. `pan_gains` renormalises so
the nearer channel carries the cue's full designed level — the hierarchy is
budgeted in peaks — so summing that pair to mono gives `(l + r) / 2` of the
designed peak. At the configured `pan_depth` of 0.45 that is **−2.7276 dB** at
full deflection, and it is arithmetic, not a defect. Comparing against unity
and calling the difference a fault would condemn the pan law for working.

What would be a fault is a *larger* loss than the law predicts, because the only
thing that produces one is phase cancellation:

| | |
|---|---|
| worst single event, measured | **−2.7276 dB** (an activation at pan 0.45) |
| what the pan law predicts | **−2.7276 dB** |
| **cancellation, therefore** | **−0.00004 dB** |
| whole-mix mono loss | −0.20 dB at correlation 0.9103 |
| worst frequency band shifted by the fold | **0.000 dB**, all seven bands |

Nothing cancels. And the reading that matters most: **own-band emergence is
identical in stereo and mono** — median +48.37 dB, minimum +8.44 dB, 0 of 50
masked in both — because folding scales the whole panned field rather than
removing any one note's channel.

### 6.4 Density, and what the schedule actually contains

| | |
|---|---|
| events | **161** — 107 duplicates, 50 activations, 1 final, 1 confirm (the drone layer), 1 unlock, 1 escape |
| max simultaneous voices | **4**, at 0.733 s, all four activations |
| below −60 dBFS | 20.86% of the timeline |
| longest silence | 0.217 s, at 34.450 s — the closing silence |
| energy above 4 kHz | 0.508% |
| energy above 8 kHz | 0.271% |
| frame mismatches, 161 events | **0** |
| placement error | **0.0 s — exactly zero** |
| mean / max frame lead | 16.17 ms / 32.82 ms |

The `confirm` event is the drone layer and it exists only in this treatment:
`v2_refined` had 160 events and no sustain under the pause. That is the one
structural difference the chosen hold makes to the schedule.

### 6.5 The ending

| | |
|---|---|
| deliberate silence at the end | 0.200 s, a schedule decision |
| last 50 ms of the decoded MP4 | **−240.0 dBFS — exact silence** |
| longest silence anywhere | 0.214 s, the closing silence |
| drone confirmation layer | present, −12.70 dBFS peak, 0.075 gain — below an activation by design |

---

## 7. Part 7 and Part 8 — the master, and frame-accurate QC

### 7.1 The two files

Both encoded from the same 1,040 PNGs and the same 24-bit WAV. **The delivery
file is not transcoded from the archive.** So the upload carries exactly one
generation of lossy video and one of lossy audio, and the archive carries one
of video and none of audio.

| | archive | **delivery** |
|---|---|---|
| path | `output/category3_v6/master/category3_test1_seed3530_archive.mkv` | `output/category3_v6/master/category3_test1_seed3530_shorts.mp4` |
| video | H.264 CRF 12, preset slow | **H.264 CRF 17, preset slow** |
| audio | PCM s24le | **AAC 192 kbps, 48 kHz stereo** |
| colour | bt709 primaries, **sRGB transfer**, bt709 matrix, yuv420p | same |
| size | 12.9 MB | **2.9 MB** |
| faststart | — | **yes** — `ftyp` → `moov` → `free` → `mdat`, verified by reading the atom table |
| SHA-256 | `56fbf1ea82b903e5…` | `d9b34f9c573543c7…` |

**The archive's audio is bit-exact.** Decoded back out of the `.mkv` and
compared with the 24-bit PCM master sample by sample: **zero difference across
all 1,664,000 samples**, and the same sample count. So the archive carries the
soundtrack losslessly and any future re-delivery from it starts with the
original audio rather than with a decode of an AAC encode.

**A fourth finding, in the encoder rather than in the work.** The delivered
stream's transfer characteristic is `iec61966-2-1` — sRGB — and not the bt709
that was asked for. `-color_trc bt709` and `-x264-params transfer=bt709` were
both tried and both were ignored: ffmpeg propagates the *input's* transfer tag,
the frames are sRGB PNGs written by Godot, and sRGB is what comes out. Rather
than leave a production config claiming something the file does not say, the
config now records `iec61966-2-1`, with the reason on the field. sRGB is the
honest tag anyway — it is what the source is, and it differs from bt709 only in
the toe of the curve.

The two encodes that bracket that change are the evidence: passing
`iec61966-2-1` instead of `bt709` produced a delivery file with the **same
SHA-256**, which is what "the flag was ignored" means measured rather than
argued. It also establishes something stronger than was claimed for the
pipeline — **the delivery MP4 is byte-reproducible**, twice from the same
frames and the same WAV. The archive is not: Matroska writes a fresh
`SegmentUID` and muxing date every time, so the two archives are the same size
to the byte and differ in hash. That is a property of the container, not of the
picture.

### 7.2 QC, on the encoded file

Every number below was read out of the delivered MP4, not out of the frames.

**Container**

| | |
|---|---|
| video | h264, 1080×1920, 30 fps, yuv420p |
| frames | **1,040** — exactly `round(34.6219 × 30) + 1` |
| duration | 34.666 s |
| audio | aac, 48000 Hz, 2 channels |

**Opening**

| | |
|---|---|
| frame 0 blank? | **no** — peak 255, mean 11.6, 17,445 bright pixels |
| ball already moving? | **yes** — frames 0 and 2 differ in **35,006 pixels** |
| hook readable on frame 0? | yes — 717×43 px at +232 levels of contrast |
| `0 / 51` readable on frame 0? | yes — counter present and clear of every UI model |
| blank frames anywhere in 1,040 | **0** (none with peak < 12, none with mean < 1.0) |

**Early and middle**

| moment | frame | lit tiles in the picture | the ledger | agree | worst tile gap |
|---|---|---|---|---|---|
| 8th activation | 46 | 7 | 7 | **yes** | 78.9 |
| 26th activation | 206 | 25 | 25 | **yes** | 73.1 |
| late 48/51 | 732 | 48 | 48 | **yes** | 137.4 |
| 49/51 | 806 | 49 | 49 | **yes** | 137.1 |
| 50/51 | 865 | 50 | 50 | **yes** | 149.9 |

The counter is written by the scene from `activated_count_at`, the same
function the tiles are lit from, so the picture agreeing with the ledger is the
counter agreeing with the ledger.

**No dead section.** Two independent readings say so.

The locked Phase 4 pacing gate, re-run on the production seed, **accepts** it
with no failures on any of its three criteria — `no_gap_over_ceiling`,
`long_gaps_are_busy`, `no_repetitive_stall`:

| window | length | ceiling | contacts | contacts/s | distinct sides | repeat ratio |
|---|---|---|---|---|---|---|
| worst body gap (45/51) | **1.703 s** | 4.0 s | 7 | 4.11 | 7 | 0.00 |
| approach 48→49 | **2.478 s** | 4.5 s | 11 | 4.44 | 10 | 0.00 |
| approach 49→50 | **1.954 s** | 4.5 s | 10 | 5.12 | 8 | 0.00 |
| final hunt 50→51 | **3.821 s** | 5.0 s | 18 | 4.71 | 14 | 0.06 |

And the picture brightens monotonically as progress accumulates, which is the
other half of "remains engaging":

| moment | frame | pixels above 200 | mean luminance |
|---|---|---|---|
| opening | 0 | 17,445 | 11.57 |
| 8/51 | 46 | 20,984 | 13.04 |
| 26/51 | 206 | 32,194 | 15.76 |
| 48/51 | 732 | 43,955 | 18.60 |
| 50/51 | 865 | 44,953 | 18.71 |
| final hit | 964 | 45,249 | 18.65 |
| confirming | 968 | 51,907 | 21.51 |
| **unlocking** | 983 | **56,827** | **21.83** |
| escaping | 992 | 32,769 | 17.06 |
| settled | 1024 | 20,442 | 15.43 |

The peak is the unlock and the fall afterwards is the gate section leaving the
ring, which is the shape the ending is supposed to have.

Every one of the 1,040 frames was also compared with the one
before it. There is exactly **one** run of identical frames in the whole video:
frames 1025–1039, fifteen frames — the designed 0.5 s `settled` hold. Nowhere
else does the picture repeat.

**What the encode cost.** The same frames, source PNG against decoded MP4:

| frame | worst-case tile gap, source | decoded | delta |
|---|---|---|---|
| 46 | 79.4 | 78.9 | −0.5 |
| 206 | 72.3 | 73.1 | +0.8 |
| 732 | 138.1 | 137.4 | −0.7 |
| 806 | 138.1 | 137.1 | −1.0 |
| 865 | 150.8 | 149.9 | −0.9 |

At most **1.0 level out of 255** on the measurement the late game turns on.

**Climax**

| | |
|---|---|
| final activation sync | on its own frame, 0 mismatches of 161 events, placement error **0.0 s** |
| confirmation pulse blown out? | **no** — 0.18% of pixels fully white, 2.57% above 200 |
| drone hold | present and correct, under the 0.92 s pause |
| gate unlock | 0.59% fully white, the gate arc reads cyan-white against orange |
| escape | readable; the ball leaves through the gate and out of frame |

**Ending**

| | |
|---|---|
| audio decay | last 50 ms at **−240.0 dBFS** |
| extra black frames | **none** — last frame peaks at 209, mean 15.4 |
| clipped final animation | no — frames 1037→1039 differ in **0 pixels**, the designed hold |
| encoding artefacts | none found; ≤1.0 level of contrast loss, 0 stray pixels |

**Synchronisation**

| | |
|---|---|
| video | 1,040 frames ÷ 30 = **34.666667 s** |
| audio | 1,664,000 samples ÷ 48000 = **34.666667 s** |
| source WAV samples | **1,664,000 — identical** |
| drift | **0.00 ms, 0.0000 frames** |
| stream start PTS | 0.0 and 0.0 |

The zero is exact rather than small: at 48000/30 a frame is exactly 1,600
samples, so every cue lands on an integer sample and there is nothing to round.

---

## 8. Part 9 — the reproducibility lock

`satisfying/tile_production.py` holds the production identity as one frozen
object with a digest over every dial. It is layered on purpose, so a mismatch
says *which layer* moved rather than only that something did.

| layer | fingerprint |
|---|---|
| production config | **`9c02d818b4052c40`** |
| audio config (`v3_hold_drone` at 30 fps) | `69b15931645aedcd` |
| safe-area config (`shorts_conservative`) | `3776358f1bf13326` |
| playback document | `e4b2c8ee78ece9ed50bda653744dfb86b6e3a6525c10660fc0e619e4dfde58c1` |
| audio PCM master | `200e7fad81ac6ed82f83d2bea6d9f80256bd2057d568761b546deba83060ac9d` |
| archive `.mkv` | `56fbf1ea82b903e57146bc1364656fbdca38c5c6739a05adc47a64bc97addc11` |
| delivery `.mp4` | `d9b34f9c573543c7f79aa2a3bca2481be11341e764609eebe3572d5bd43528ed` |

The whole block is written to `output/category3_v6/production_identity.json`.

**The production identity**

| | |
|---|---|
| seed | **3530** |
| simulation | 17 sides × 3 tiles = 51 activatable, gravity 0, speed 85 wu/s, one ball, no assistance |
| run | 32.143 s, 158 contacts, 51/51, final tile **#50** |
| climax | `standard` timing, **2.479 s**, total render **34.622 s**, **1,040 frames** |
| composition | arena width **0.765**, centre offset **−0.060**, hook top 0.075, counter top **0.745**, trail 0.09 s, ball draw 1.45× |
| hook | `HIT EVERY TILE TO ESCAPE` |
| audio | `v3_hold_drone` — A minor pentatonic, 11 notes over 220–880 Hz, spatial pitch, pan depth 0.45, drone hold, progression on |
| ducking | `activation_duck = False`; lead 0.080 s, tail 0.140 s, depth 0.32 available and off |
| encode | libx264 CRF 17 preset slow, yuv420p, bt709 primaries / sRGB transfer / bt709 matrix, AAC 192k/48 kHz, faststart |
| archive | CRF 12, pcm_s24le |

**The run is byte-identical to Phase 5's.** The playback document's `digest`,
`collisions`, `activations` and `flight` are all unchanged from
`output/category3_v5/`; the only field that moved is `completion`, and inside it
only the escape's length, because the frame the ball has to leave moved. The
physics was not touched.

**Reproducing it**

```
$env:GODOT_BIN = "...\Godot_v4.7.2-stable_win64.exe"
python -m satisfying.tile_phase6_cli export     # the canonical playback document
python -m satisfying.tile_phase6_cli frames     # 1,040 PNGs, Godot
python -m satisfying.tile_phase6_cli audio      # the schedule, the PCM master, every measurement
python -m satisfying.tile_phase6_cli safearea   # the Shorts gate, and the overlay proofs
python -m satisfying.tile_phase6_cli master     # the archive and the delivery file
python -m satisfying.tile_phase6_cli phone      # mono, the phone speaker, 270x480
python -m satisfying.tile_phase6_cli qc         # frame-accurate QC on the encoded file
python -m satisfying.tile_phase6_cli verify     # determinism, at every layer
python -m satisfying.tile_phase6_cli identity   # the lock, with digests
```

`verify` checks the four layers that are exactly reproducible — the run
re-simulates to the same digest, the schedule builds identically twice, the
waveform renders to the same SHA-256 twice, and the written master matches a
fresh render. The encoder is *not* claimed to be bit-exact, because x264 is
free to differ between builds; what is checked there is the decoded result,
which is §7.2.

Do not run the test suite and a Godot render at the same time — Phase 3's
warning still applies.

---

## 9. Outputs

All under the un-gitted `output/category3_v6/`.

| path | what |
|---|---|
| **`master/category3_test1_seed3530_shorts.mp4`** | **the upload** |
| `master/category3_test1_seed3530_archive.mkv` | the archival master, CRF 12 + PCM |
| `playback/seed_3530_standard.json` | the canonical playback document |
| `climax30_standard/seed_3530/` | the 1,040 source PNGs |
| `audio/seed_3530_v3_hold_drone.wav` | the 24-bit PCM master |
| `audio/seed_3530_v3_hold_drone.measure.json` | every audio measurement, both instruments, master and phone |
| `score/seed_3530_v3_hold_drone.json` | the machine-readable audio schedule |
| `safe_area/safe_area.json` | the three models' verdicts, and the type's measured boxes |
| `safe_area/*_shorts_conservative.png` | the overlay proofs, nine moments |
| `safe_area/*_plain.png` | the same frames without the overlay |
| `phone/phone.json` | mono, phone-speaker and 270×480 readings |
| `phone/frames_270x480/` | the phone-size render |
| `qc/qc.json` | the frame-accurate QC report |
| `qc/frames/` | the frames decoded back out of the delivered MP4 |
| `qc/decoded.wav` | the delivered audio, decoded, for the true-peak check |
| `production_identity.json` | the reproducibility lock |
| `hook/` | the Part 2 comparison renders, both hooks, both sizes |

---

## 10. Tests and regression

`tests/test_tile_escape_phase6.py` — **45 tests**, covering every item the
brief listed:

| the brief's requirement | tests |
|---|---|
| activation duck determinism | built twice and compared; built again from a freshly simulated document; the shaping function is monotone and zero outside its window |
| duck applies only to intended bed events | at depth 0.5 the set of touched kinds is exactly `{duplicate}`; at depth 0.9 not one activation, final, unlock, escape or confirm event moves |
| event hierarchy remains intact | the configured gains, and the rendered master measured on the master, through a mono fold and through `phone_filter` — the order never inverts and the gaps stay above 6 dB and 3 dB |
| final hook/config is deterministic | the hook is pinned in the production config and in the scene's `HOOK_DEFAULT`; the production fingerprint is stable and moves with any of nine dials |
| safe-area config parses and remains stable | three models round-trip through JSON, all fingerprints distinct, the fingerprint moves with any of four dials, and six malformed configurations are refused rather than measured |
| canonical playback unchanged | the document is byte-compared before and after the score, the render, the safe-area report, the geometry and the identity have all read it; it still passes `verify_document`; and the same seed re-simulates to the same digest |
| final audio length matches presentation timeline | `round(total_render × fps) + 1` frames, `total_samples == frames × 1600`, and every climax beat read from `completion["timeline"]` by state name |
| no clipping | zero clipped samples, peak under the ceiling, true peak under −1.0 dBTP, and the limiter asserted idle |
| final video/audio synchronisation | zero frame mismatches and exactly 0.0 s placement error across all 161 events |
| production config digest stability | stable across calls, equal to a fresh default, and distinct under nine separate field changes |

Plus regressions for the three defects this phase found, and for the four
things that made them findable:

* the duplicate bed is empty inside the measurement window on the densest seed
  — the fact that made the prescribed fix inapplicable;
* `band_masking_report` agrees with numpy's transform to 1e-9 and rejects an
  out-of-band tone by more than 40 dB;
* every activation clears 3 dB in its own band, on the master and through a
  phone;
* the mono fold loses only what the pan law predicts;
* a fully retracted gate tile is hidden and `maxf(0.02, 1.0 - e)` is asserted
  gone;
* the counter's glyph box clears every model's title block and the hook's
  clears every top bar;
* no tile is under the UI on any of the five pacing-valid seeds, the last four
  tiles to light are clear on each, and the arena clears the rail without
  having been pushed off the left edge;
* Python and GDScript agree on all five shared composition constants, the
  camera offset is applied in camera units, and the projection is still a pure
  scale plus a translation.

### Full-suite comparison

Both runs are `python -m pytest -q -p no:randomly`, this branch in its own
worktree and the base in a second detached worktree checked out at `997c161`,
so the comparison is a diff of two measured failure sets rather than a
restatement of what Phase 5 recorded.

| | failures | passed | skipped | wall |
|---|---|---|---|---|
| `997c161`, the base | **18** | 6,011 | 441 | 36 m 02 s |
| this branch | **18** | **6,057** | 440 | 36 m 39 s |

The delta accounts for itself exactly, and the +1 is worth spelling out because
it is the kind of difference that looks like a change and is not one:

```
6,011  base passes
  +45  Phase 6 tests
   +1  test_every_recorded_audit_agrees_with_its_document
-----
6,057        skipped: 441 - 1 = 440
```

That one test is Phase 3's, it is marked `requires_evidence`, and it skips when
`output/category3_v3/` is absent. The base was run in a **freshly created
detached worktree**, which has no `output/` at all, so it skipped there; this
worktree has carried that directory since Phase 3, so it ran and passed. Both
halves were confirmed directly by running that single test in each tree. It is
a property of which worktree holds the un-gitted evidence, not of anything
Phase 6 did.

**The two failure sets are identical, name for name** — diffed, not eyeballed.
**Not one of the eighteen is a Category 3 test.** They are the fingerprint
Phases 2, 3, 4 and 5 all recorded, and they split three ways:

| n | what | why it fails |
|---|---|---|
| 12 | `test_race2_v30_stage`, `v301_stage`, `v311_track` (2), `v321_geometry`, `v32_final` (6), `v33_bookends` | stale cross-workstream branch guards that diff `origin/main...HEAD` and reject anything outside their own allowlist |
| 5 | `test_sloped_v251_world` (4), `test_sloped_v252_world` (1) | they read camera files under the un-gitted `output/sloped_race_v1/`, which is not in this worktree |
| 1 | `test_neon_proof::test_a_missing_godot_is_reported_rather_than_raised` | an environment path assertion |

None indicates a regression, and per Phase 4's note the comparison that matters
is against the base and not against any absolute number. Per
[[suite-has-14-known-failures]] a failure above the base is real until proven
otherwise; none appeared.

**Two failures did appear on the way, both caused by this phase, and both were
fixed at the source rather than by relaxing the check.** Widening the frame in
world units lengthened every preset's escape, which (a) pushed the unused
`stretched` timing preset 0.039 s past the 2.6 s ceiling its own test enforces
— its tail hold went 0.40 to 0.33 s, because the axis that preset exists to
vary is the front beats — and (b) moved the frame count Phase 5 pinned from
1,038 to 1,040. The second is the one test in this phase whose asserted number
changed; it was re-measured against both the 1,040 PNGs on disk and `ffprobe`
on the delivered MP4, and renamed from `..._phase4_render_...` to
`..._phase6_render_...` because that is now the render it cross-checks.

---

## 11. Decision

**PRODUCTION MASTER APPROVED.**

Against the gate's seven conditions:

| condition | evidence | verdict |
|---|---|---|
| the encoded master passes visual QC | 1,040 frames at 1080×1920/30, 0 blank, 0 stray pixels, the only repeated frames are the designed 0.5 s hold, ≤1.0 level of contrast lost to the encode, picture and ledger agree at five checkpoints | **passes** |
| the encoded master passes audio QC | −1.754 dBFS / −1.587 dBTP decoded, 0 clipped, limiter never engaged, −18.89 LUFS, exact silence in the last 50 ms | **passes** |
| safe areas pass | 0 of 51 tiles obstructed on all five seeds under the gate model, every dark tile clear at 48/51, 49/51 and 50/51, final tile clear, ball never hidden, hook and counter clear of all three models | **passes** |
| activation hierarchy is clear | +12.46 dB on the master, +12.08 in mono, +14.95 on a phone; 0 of 50 activations masked in their own band in any of the three | **passes** |
| the selected hook is readable | 43 px cap height at +232 levels, clear of every UI model at 1080×1920 and at 270×480 | **passes** |
| no sync defects exist | 0 frame mismatches of 161 events, 0.0 s placement error, 0.00 ms drift between the encoded streams, both starting at PTS 0 | **passes** |
| no unresolved production issue remains | the three defects found are fixed and each has a regression | **passes, with one disclosure** |

**The disclosure.** One activation in 250 across five seeds does not clear 3 dB
in its own band: seed **6132**'s eighth activation, at +0.91 dB, because two
tiles sharing the 587.3 Hz fundamental light 200 ms apart. Seed 37169 has the
same collision at 133 ms and clears by +3.27 dB. It is reported rather than
smoothed, it is a property of an activation order rather than of the mix, and
**seed 3530 — the seed being shipped — contains no such collision**, with a
worst activation clearing by +8.44 dB on the master and +8.09 dB through a
phone. It does not affect the master this phase delivers.

**What is still settled by measurement rather than by an ear.** Phase 5 said no
ear had heard these files and that three of its eight criteria were bounded by
measurement rather than decided by listening. Phase 6 received the creative
choice — seed 3530, the drone hold — as made, and did not reopen it. So the
claim here is narrower than "this sounds good": it is that the file is correct,
reproducible, unclipped, in sync, legible under the player's UI, and free of the
three defects found. Whether it is *satisfying* remains a judgement a person
makes by watching it, and that has not been delegated to a number.

---

## 12. Upload recommendation

Upload exactly this file:

```
output/category3_v6/master/category3_test1_seed3530_shorts.mp4
```

2.9 MB, 1080×1920, 30 fps, 1,040 frames, 34.667 s, H.264 CRF 17 + AAC 192 kbps
at 48 kHz, faststart, SHA-256 `d9b34f9c573543c7f79aa2a3bca2481be11341e764609eebe3572d5bd43528ed`.

Keep `category3_test1_seed3530_archive.mkv` as the archival master. It carries
the same picture at CRF 12 with PCM audio, so any future re-delivery — a
different platform, a different bitrate, a re-cut — can be made from it without
a second generation of lossy audio.

The video carries no title, description, tags or thumbnail, deliberately: those
belong to whatever uploads it, and a video with its own metadata baked in
cannot be re-titled without a re-encode.

**Nothing was uploaded and nothing was merged.**

---

## 13. Recommendation for a Phase 7, if there is one

1. **Watch it.** Three of Phase 5's eight criteria and the whole question of
   whether the thing is satisfying are still settled by a person, not a
   measurement, and the file now exists to be watched.

2. **The same-pitch collision is the only open audio question.** One
   activation in 250 arrives inside a still-ringing channel at its own pitch.
   The cheap fix is a seed-acceptance criterion — reject a run whose activation
   order puts two tiles of the same pitch within 200 ms — which costs nothing
   structural and uses machinery Phase 2 already built. Re-pitching by
   collision order would be the wrong fix: it would break the property that a
   tile's note is a function of where it is and nothing else.

3. **`shorts_strict` is the early-warning system.** The composition clears the
   conservative model with 18.9 px to spare and fails the strict one. If
   YouTube's rail grows, that is the number that moves first, and the fix is
   already characterised: §4.3's table says what each further step costs.

4. **The broadband masking instrument should probably be retired, not kept
   beside the band one.** It is right for the three single loud events and
   wrong for the fifty pitched ones, and keeping both invites someone to quote
   the wrong number again. A better shape would be one instrument that picks
   its own bandwidth from the event's kind.

5. **Nothing else in the locked system should move.** Physics, arena, speed,
   gravity, pacing gate, climax structure and soundtrack system are all doing
   their jobs and have been measured doing them across six phases.
