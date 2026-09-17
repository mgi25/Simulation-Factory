# V32: the Race #2 production Short

**Branch** `v32-race2-production-final`, from
`origin/v311-track-visibility-polish` at `fa39d7a`.
**Scope** presentation only. Four files:

```
race2/presentation.py            the film clock, and the three marks' placement
tools/race2_v32_short.py         evidence -> audio -> overlays -> mux -> qc
tests/test_race2_v32_final.py    56 tests, including the locks as a diff
docs/race2_v32_production.md     this
```

plus `docs/validation/race2/v32_final/`, which is measurement output. No
physics, no replay, no seed, no course, no mechanism, no camera, no cut, no
environment, no light, no material and no track profile is touched, and
`test_the_branch_adds_only_presentation` asserts the whole change set by name
so the scope is a test rather than a claim.

---

## 1. What shipped

```
exports/race2_v32_final/
  race2_switchyard_final.mp4              the upload candidate
  race2_switchyard_master.mp4             the locked picture, no marks, no sound
  race2_switchyard_final_visual.mp4       the marks, no sound
  race2_switchyard_final_phone_270x480.mp4
```

| | |
|---|---|
| race | SWITCHYARD, hero seed 8 |
| camera | V31 RB readability |
| environment | `contained_bay_v301` |
| track | V31.1 Variant B |
| resolution | 1080 x 1920 |
| frame rate | 60 fps |
| frames | **1150**, frame 0 to frame 1149, contiguous |
| runtime | **19.1667 s** |
| temporal omissions | **0** |
| integrated loudness | **-14.18 LUFS** |
| true peak | **-1.93 dBTP** |
| duplicate frames | 0 |
| black frames | 0 |
| video | H.264, CRF 17, preset slow, yuv420p, `+faststart` |
| audio | AAC 256 kbit/s, 48 kHz stereo |
| file | 13.2 MB |

`python tools/race2_v32_short.py all` rebuilds all four from the rendered
master, and runs its own QC: **38 checks, all passing**, in
`docs/validation/race2/v32_final/qc.json`.

### The 19.150 against the 19.1667

The brief names the runtime as 19.150 s and that is the **camera track's**
duration. The renderer's rule is `range(first, round(duration * fps) + 1)`, so
it writes frames 0 to 1149 inclusive - 1150 frames, which at 60 fps is
19.1667 s of film. The last frame's *timestamp* is 19.150 s.

Both numbers are correct about different things, and the distinction is
load-bearing rather than pedantic: the soundtrack is built to the film's length
and is 920000 samples, which is exactly 1150 x 800. Taking 19.150 would make the
audio one frame short of the picture, which is the drift that shows up as a click
at the end of an export. V31.1's document already records 1150; this restates it
because the brief does not.

---

## 2. The locks, verified

`python tools/race2_v32_short.py locks` writes
`docs/validation/race2/v32_final/locks.json`. Three kinds of evidence:

| layer | source files vs `fa39d7a` | regenerated report | fields |
|---|---|---|---|
| physics | 7 identical | `events_switchyard_8.json` | **697 identical** |
| camera | 6 identical | `read_RB.json` | **167 identical** |
| environment | 2 identical | — | — |
| track | 1 identical | `track_measure.json` | **6866 identical** |

The regenerated reports are the strong half. Each was rebuilt on this branch,
from this branch's own render, and compared field by field with the one the base
commit ships:

* **physics** — `tools/race2_camera.py --course=switchyard --seed=8` reproduces
  the committed race evidence exactly, every field but `wall_seconds`, which is
  a measurement of this machine rather than of the race. The replay carries its
  own `digest` `751031348936808792ad2fac667bfdfb6e726dca7520ffdaf19429c6a2f7f539`
  and `event_digest` `51078e8d31e56f53993c6ee9aa61b482a6757942a422fb43f533336983016502`.
* **camera** — `tools/race2_v31_camera.py --only=RB` reproduces `flow_RB.json`
  and `read_RB.json` byte for byte. The delivered track is 4 cuts,
  `release` 0.02–2.23, `upper` 2.23–9.02, `middle` 9.02–12.68, `run_in`
  12.68–19.15.
* **track and environment together** — V31.1's own segmentation instrument was
  re-run over frames rendered on this branch, and **all 46 of its variant fields
  and all 13 moments come back identical**: `track_L` 76.93, spread 39.05,
  `wall_face_L` 80.95, crown 88.41, `edge_step_dL` 7.46, cradle 35.62,
  `track_warmth` +4.65, `clipped` 0.00%. A render chain that reproduces a
  46-field photometric report cannot have moved the material, the room, the
  light, the lens or the race.
* the render's own census matches `v311_track/cost.json` for B exactly: 326 mesh
  instances, 93404 triangles, 25420 course triangles, 11 runs.

### The instrument bug in the lock check

The first build of `locks` hashed each file's bytes and compared them with the
base commit's blob. It reported **all sixteen locked files as changed** while
`git diff` against the same commit returned nothing at all. The cause is
`core.autocrlf = true`: the working tree carries CRLF and the object store
carries LF, so a raw hash compares two different encodings of the same file. A
lock instrument that cannot pass is worse than no lock instrument, because its
failure looks like a finding. The verdict now comes from `git diff`, which
applies the same filters to both sides; the raw hashes are kept in the report as
a record of what was measured, not as the test.

A second one, in the same stage: the report comparator returned early on
`base is None`, and both reports are full of legitimate nulls — `race.failure`,
every racer's `lost_at`, every moment's `structure` on a frame with no structure
in it. Comparing the committed file **with itself** returned 28 differences.
`_ABSENT` is now the sentinel for a key that is not there, which is the case that
matters.

---

## 3. The comeback claim that did not survive

The brief asks for `[WINNER COLOR] WINS / 6TH -> 1ST` and then asks for the 6TH
to be checked. It does not hold.

V31's production preview computes the comeback as the worst index the winner
ever occupies in `outcome.rank_series` and prints it. On this seed that is 6.
Measured over the film's own 1149 samples, m7's rank history is:

| rank | total held | longest single run |
|---|---|---|
| 1 | 5.367 s | 3.600 s |
| 2 | 3.450 s | 2.267 s |
| 3 | 6.317 s | 6.167 s |
| 4 | 2.183 s | 1.100 s |
| 5 | **1.617 s** | **0.933 s** |
| **6** | **0.217 s** | **0.217 s = 13 frames** |

**m7 is sixth for thirteen frames**, once, at 3.13–3.33 s, in the middle of the
scramble through the studs. It is an instant of a sort order, not a position a
viewer could see it in, and a card that names it is a fabricated comeback.

The race's own checkpoint ladder — the instrument the simulation records on
purpose — agrees with the duration-weighted history and not with the preview:

```
release 4   first_event 5   quarter 4   half 3   three_quarter 2   finish 1
```

So the card says **5TH -> 1ST**, and both instruments have to agree before it
will render: `comeback_rank` takes a **floor** of 0.5 s (30 frames) on how long
a rank must be held, reports every run it rejected, and
`stage_evidence` refuses to build if the checkpoint ladder disagrees with it.
`test_the_six_place_claim_is_false` asserts the rejection rather than only the
answer, and `test_comeback_rank_rejects_a_blip` tests the rule on synthetic runs
so it is the rule under test and not this seed.

5TH -> 1ST is still a real comeback: m7 is fourth or fifth for most of the
film's first 4.7 s, is third for the next 6.2 s, takes second at 10.85, leads from
13.12, loses it again at 14.38 and takes it back at 15.57 — **0.25 s before the
line**, winning by **0.0667 s**.

---

## 4. The winner's colour, measured on the rendered frame

The brief asks not to assume the label from Race #1. It was not assumed.

`race2_scene` paints racer `info["id"]` with `lab_palette.marble(id)`, and
`MARBLE_COLOURS[7]` is `#F0559B`. To check that this reaches the picture, V31.1's
`--track=racers` diagnostic labels each racer by index in the renderer itself,
and the labelled pixels were read out of the delivered frames:

| id | rendered mean RGB | rendered hue | palette hue | name |
|---|---|---|---|---|
| 0 | (230, 53, 50) | 1.0 | 355.8 | RED |
| 1 | (30, 90, 190) | 217.5 | 219.2 | BLUE |
| 2 | (65, 180, 87) | 131.5 | 142.3 | GREEN |
| 3 | (222, 196, 75) | 49.4 | 47.0 | YELLOW |
| 4 | (231, 146, 53) | 31.5 | 23.0 | ORANGE |
| 5 | (159, 59, 201) | 282.4 | 271.8 | PURPLE |
| 6 | (102, 206, 198) | 175.8 | 180.0 | TEAL |
| **7** | **(218, 104, 161)** | **330.1** | 332.9 | **PINK** |

m7 renders 2.8 degrees from its own albedo and **47.7 degrees from its nearest
neighbour in the rendered field** (purple, 282.4). PINK is not a judgement call.
The card's lozenge carries the albedo `#F0559B` unmodified, which is the sample a
viewer matches against the ball.

---

## 5. PICK A COLOR

### 5.1 It is two lines, and that is a measurement

V24 sets PICK A COLOR in one line at 96 pt because it was sized against V20's
*held opening frame*. Measured on the delivered face in this clone, that line is
785 px of ink with 13.5% clear each side, and its cap height is 71 px —
**17.8 px at the 270x480 a phone feed scrubs at**. V31's preview ran the same
line at 104 pt, which is 19.2 px.

This opening is not a held frame. It is live footage, and the eight racers are
low in it: measured over the mark's whole life they occupy **y 806–1079**, which
leaves a usable band 640 px tall above them. A two-line block uses it.

| | one line 96 (V24) | one line 104 (V31) | one line 109 | **two lines 201** |
|---|---|---|---|---|
| ink width | 785 | 852 | 892 | 758 / **786** |
| margin each side | 13.5% | 10.4% | 8.5% | **13.6%** |
| cap height | 71 px | 77 px | 80 px | **148 px** |
| **cap at 270x480** | 17.8 | 19.2 | 20.0 | **37.0** |

The size is not chosen: `hook_size` fits the **rendered ink** of the widest line
to the margin V24's shipped mark actually has, then walks down by ones to absorb
hinting. Same face, same warm white, same soft shadow, same 0.09 tracking, same
twelve glyphs, through `overlays._shadowed`. Only the break is new, and the mark
is **1.93x** the phone-scale cap height of the one the brief calls small.

### 5.2 Where it sits, and what it clears

The block is centred in the band between the frame's own 96 px gutter and the
topmost racer pixel less V24's 70 px clearance. On this film that is baselines
375 and 606, ink measured at y 229 to 608, and **200 px of clear air** between the last
line and the nearest marble. The mark cannot cover the eight things it is
pointing at, and the clearance is reported rather than assumed.

### 5.3 When it goes

V24's timing exactly: **up on frame 0, fading 1.05 to 1.30 s.** No fade *in* —
a `fade=t=in` starting at zero makes the first frame transparent and the first
frame is the one the hook exists for. The film's first camera cut is at
**2.233 s**, so the mark is gone 0.93 s before the lens changes and never runs
into the racing. There is no frozen hold and no course preview: race motion
starts on frame 0, which is the V24/V26 philosophy the brief asks to restore.

---

## 6. The winner's ring

| | |
|---|---|
| marble | **m7**, the actual winner |
| opens | **15.8167 s — the frame it crosses** |
| runs | 0.70 s, 42 frames |
| radius | 30–31 px |
| frames the course blocks | **0 of 42** |
| frames off the frame | **0 of 42** |

V22.1 opened its ring 0.200 s after the crossing; V24's payoff lab measured that
this put **one frame of it on a visible marble** and the other 0.683 s on the
finish gantry's rail. V31's preview inherited a 0.180 s delay. Here the ring
opens **on** the crossing, which is what makes Part C's "through the crossing"
literal.

It can, because this finish is not Race #1's. Measured on the delivered frames —
projecting m7 and counting how much of the disc carries its own hue — the winner
is on screen **continuously from 15.23 s to the last frame**, with two
single-frame dips. Both were looked at rather than assumed, and neither is
occlusion by the environment or the track: at 16.217 s **cobalt (m1) crosses in
front of pink**, and at 17.950 s it does it again. That is a race event.
`ring_track` runs both tests — `spine.blocked` for course geometry and the frame
itself for everything else — refuses to composite on a geometric block, and
reports a competitor rather than refusing.

### The flash that was not there

The first build of this pass shipped the ring **one frame late**, and no report
said so. Every placement number was right, `frames_blocked` was 0, the contact
sheets looked correct, and the delivered file was missing the only part of any
mark in this film that is synchronised to an event.

`sloped_short` documents the mechanism: an ffmpeg `setpts` offset that is not a
whole tick lands the sequence between two frames and the first one is never
composited. The offset here came from `evidence.json`, where it had been written
as `round(start, 4)` — **15.8167 against the frame's own 15.816666…**, three
hundredths of a millisecond late, and `between(t,15.8167,…)` therefore excludes
frame 949 and opens the mark on 950. Rounding a number for a report and then
reading it back as an instruction is enough to lose a frame.

What found it is `qc`'s `_mark_presence`, which decodes the **delivered Short**
and the **delivered master** at the same frame indices and differences them: the
two files are the same picture with three plates on one of them, so the
difference between them *is* the marks. On the crossing frame it measured 0.924
of 255 — encoder noise, not a mark — against 11.255 a fifth of a second later.
No instrument that looks at the plan could have caught it, because the plan was
correct.

Every window in the graph is now stated in whole frames, `between(t,948.5/60,
990.5/60)`, with the offset as `949/60`, and three tests hold it: the windows'
numerators against the evidence, the offset's numerator against
`ring.from_frame`, and the measured difference on the crossing frame itself.

---

## 7. The payoff

```
   [PINK] WINS
   5TH -> 1ST
```

`v24_payoff`'s `plate` style, its lab's own recommendation, built rather than
rebuilt: the type is fitted to the gutter by measurement, the lozenge is m7's
exact albedo with the word reversed out of it at **3.09:1** — above the WCAG
large-text floor — and the colour area is **54268 px**, about 13x the `chip`
style's ball and 23x the dot the shipped `end_fact` names a winner with.

### V24's band does not work on this film

`v24_payoff.PAYOFF_BAND` is `(297, 548)`, measured on Race #1's finish lens. On
this film, over the card's whole life, that band **peaks at 255 luma and has
racers in it**. `card_band` measures the real one on the delivered frames, under
two conditions:

* no row may exceed 130 luma anywhere across the text corridor x 96–984, on any
  frame the card is up — the *maximum*, not the mean, because a card on a
  chequer lands half its glyphs on the dark tile;
* no row may carry a marble that **has not finished yet**. A marble parked on
  the deck is scenery; one still coming down the channel is the race.

The answer is **y 97–372, 275 px, max luma 84.1**. Everything from 372 to 763
has a still-racing marble in it at some point between 16.82 s and the end.

The card is then aligned to the band's **floor**, not its ceiling — the floor is
where the race is and the ceiling is where a phone's own furniture is. That is
worth 50 px of top margin and costs nothing; the trade was measured:

| ink top | ink bottom | frames crossing a racing marble |
|---|---|---|
| **147** | **372** | **0** |
| 171 | 396 | 2 |
| 221 | 446 | 5 |
| 296 | 521 | 13 |

The delivered card's ink is `(112, 147, 966, 372)` — the lowest zero-intersection
position there is.

### Timing

Crossing 15.8167 → **card up at 16.8167**, V24's 1.0 s recognition beat, the
middle of its lab's 0.8–1.5 s band → held to the last frame, **2.35 s**. The
ring has been gone for 0.30 s when it arrives, so the two marks never overlap,
and the winner is still on screen underneath a line that has already said PINK.

---

## 8. Audio

`audio.marble.build_race_audio` unchanged, on the same replay the pictures came
from. Race #2 reaches it with no `start.paddle`, `start.panel` or `start.rotor`
in its actuator set, so the gate, trapdoor and mixer voices return nothing and
are absent — correctly, because this machine has none of them. What is placed:

```
ambience 1   rolling 1   impact 239   crossing 8   music 1
```

| | |
|---|---|
| length | 920000 samples = 1150 frames x 800, exact |
| peak in | -11.06 dBFS |
| bus compressor | 4.62 dB |
| peak out | -2.06 dBFS, limiter idle |
| **integrated** | **-14.18 LUFS** |
| **true peak** | **-1.93 dBTP** |
| loudness range | 3.30 LU |

−14.18 LUFS is the production reference the accepted Shorts are measured
against (`loudnorm=I=-14:TP=-1`), and −1.93 dBTP is 0.93 dB under the ceiling.

**Mechanism impacts, Part G, measured rather than designed.** Race #2 has 32
`mechanism_hit` events across the drum, sweep, pair, last and studs.
`sloped.presentation.impacts` — the established instrument, which fires on a
velocity residual gravity cannot explain — puts a cue within 0.12 s of **31 of
the 32**. Nothing was added to make that true; a blade strike is a large contact
impulse and the existing chain already hears it.

No visual timing was changed to fit the audio. The soundtrack is derived from
the film, in that order.

---

## 9. Phone review — 270x480

`docs/validation/race2/v32_final/phone_review_*.png`, six sheets, sampled from
**the delivered `race2_switchyard_final.mp4`** every 30 frames.

**Decoded by frame index, not by `fps=`.** The first attempt used `-vf fps=2`
and it returns frames that are not the ones it names: the frame it handed back
for t=0 measures a racer-band mean of 25.4 against the source's 44.0, while
frame 0 selected by index matches the source at 42.7. A review sheet silently
off by some frames is a review of a film nobody is shipping. Every tile now
carries its own `n=` in the caption.

Against the brief's six questions, at 270x480:

1. **PICK A COLOR legible** — yes, 37 px of cap height, two lines, 13.7% gutter.
2. **Marbles distinguishable** — yes. Eight hues separated by hue *and* value,
   and V31.1 measured the weakest racer at 26.04 ΔE from the track.
3. **Track readable** — yes; V31.1's traceability measure returns 98–100% of the
   frame width at every racing moment, and Variant B's 7.46 L\* crown-to-face
   step is the one difference visible at this size.
4. **No overlay hides a racer** — proven, not looked at: 200 px of clearance on
   the hook, 0 blocked frames on the ring, 0 frames of racer intersection on the
   card.
5. **Winner obvious** — the ring opens on the crossing with a flash and the word
   WINNER, on a marble that is visible for every one of its 42 frames.
6. **Payoff obvious** — a card 854 px wide, most of it a pink
   lozenge with PINK reversed out of it,
   held for the last 2.35 s.

---

## 10. Motion review

Watched as six spans of the delivered file rather than as metrics.

| span | what it is |
|---|---|
| 0–2 s | the hook. Eight marbles in a row on frame 0 under the mark; the floor goes; by 1.0 s they are large and tumbling. The mark is gone by 1.30. |
| 2–6 s | the drum. The pack meets the orange blade wheel at 2.2 and is scattered through it; the field strings out by 5.5. |
| 6–10 s | the sweep and the first hairpins. The channel reads as a banked kerb; the pack is 3–5 marbles wide. |
| 10–14 s | the switchbacks and the pair. Pink moves from third to second at 10.85 and leads from 13.12. |
| 14–17 s | the final sprint, and it is a two-marble race: pink and green side by side from 14.0 to the line, pink taking it back 0.25 s out. The ring lands at 15.82. |
| 17–19.17 s | the card, with the winner still rolling underneath it and the rest of the field arriving through 18.75. |

The one honest weakness is inherited and stated in V31 §14.2: **8.0–8.5 s is the
thinnest section of the film**, where the field is genuinely strung out and the
camera has few racers to hold. It is a pacing question, not a presentation one,
and it is locked.

---

## 11. Production cleanliness — Part K

The delivery filter graph composites exactly three images over the master and
nothing else. The tests build the **generated** graph rather than grepping the
function body — a test that reads the source is really a test of its comments —
and assert that `overlay=0:0` appears three times and that none of `drawtext`,
`drawbox`, `V31`, `V32`, `control`, `hstack`, `vstack`, `xstack`, `pad=`,
`track=mask`, `track=bands`, `geq` or `colorchannelmixer` appears in it at all.

`test_the_film_is_never_re_timed` asserts the same graph contains no
`minterpolate`, `tpad`, `trim`, `concat`, `reverse`, `loop`, `fps=`,
`framerate=`, `setrange` or `select=`, and exactly one `setpts` — the whole-frame
offset that places the ring sequence, whose numerator is checked against the
evidence.

The only text in the film is `PICK A COLOR`, `WINNER`, `PINK`, `WINS`, `5TH` and
`1ST`.

---

## 12. The suite, and the nine failures that are not this pass

`python -m pytest -q` on this branch: **2920 passed, 9 failed, 342 skipped**
(17:48). Every one of the nine was reproduced with V32's four files *moved out
of the tree*, and all nine fail identically without them. None names a V32 file.

**Six are a fresh worktree missing gitignored generated input.** This clone has
never run the Race #1 or neon pipelines, and `output/` is gitignored:

| test | wants |
|---|---|
| `test_neon_proof::test_a_missing_godot_is_reported_rather_than_raised` | `output/neon_v11/neon_7.json` — the tool reports the missing replay *before* it reaches the Godot check the test is about |
| `test_sloped_v251_world` ×4, `test_sloped_v252_world` ×1 | `output/sloped_race_v1/cameras_v221_5432.json` |

**Three are predecessor branch-scope tests.** Three passes carry an assertion
that the whole diff against *their* base contains only *their* files. They are
green on their own branch and go red on every successor:

| test | why it is red at `fa39d7a` |
|---|---|
| `test_race2_v30_stage::test_this_branch_changes_no_physics_camera_or_course_module` | `race2/cinematography.py`, `race2/rig.py` — V31's work |
| `test_race2_v301_stage::test_this_branch_changes_no_physics_camera_or_course_module` | the same two |
| `test_race2_v311_track::test_the_branch_changes_only_render_and_measurement` | its own `ALLOWED` omits the seven files in `docs/validation/race2/v311_track/` that the same branch shipped |

V32 adds no new failure today, but it will add one to that third group **once it
is committed**: `test_race2_v311_track::test_no_locked_package_moved` is
parameterised over `LOCKED_PREFIXES`, which includes `race2/`, and this pass adds
`race2/presentation.py`. That lock is **V31.1's brief**, correctly stating that a
track-material pass may not touch the package; it is not V32's, whose brief asks
for exactly this layer. The module is the Race #2 counterpart of
`sloped/presentation.py` and belongs beside its siblings; nothing in the
simulation, the camera or the renderer imports it, and `test_race2_isolation` —
the test that actually guards the package's boundaries — passes, all seven of it.

The precedent is followed rather than broken: **V31.1 did not retarget V30.1's
scope test when it made it red**, and V32 does not retarget V31.1's. Editing a
predecessor's test is the thing these tests exist to make visible.

`test_race2_v32_final.py` itself: **56 passed**, and its own scope test does not
repeat V31.1's bug — `docs/validation/race2/v32_final/` is an allowed prefix, and
it reads `git status --porcelain -uall` as well as `git diff`, so it can see the
files this pass adds before they are committed.

---

## 13. Remaining weaknesses

1. **The card's text contrast is 3.09:1, not 5.26:1.** V24's lab measured warm
   white on *purple* at 5.26; pink is a lighter hue and the same white on it is
   3.09. That clears the WCAG large-text floor and it is the smallest margin any
   mark in this film has. Graphite on pink would be 4.96:1 — a real improvement
   and a change to the shipped drawing, which this pass is not the place for.
2. **6.4% is the card's top margin as a fraction of the frame** (ink at y 147).
   It is the lowest the band allows without crossing an arriving racer, and it
   sits higher in the frame than Race #1's card does. If a platform's own header
   proves to crop it, the fix is the card's size rather than its position, and
   that means parameterising `v24_payoff`'s band.
3. **The winner is briefly overtaken visually by cobalt**, twice, one frame each
   time, inside the ring's life. Nothing to fix — it is the race — but a viewer
   freeze-framing 16.217 s will see the ring around a mostly-blue pixel cluster.
4. **The opening's first half second is dark.** On frame 0 the eight are a thin
   lit row inside the start structure; they are not large and unmistakable until
   about 0.8 s. That is the locked RB camera's opening move and the brief locks
   it.
5. **8.0–8.5 s**, inherited from V31 and stated above.
6. **The cradle is still behind its own rail**, inherited from V31.1 §15.1. The
   viewer never sees the road; they see the wall of the road.

---

## 14. Is this the Race #2 production baseline?

**Yes.** Everything the brief asked to be verified has been, with numbers:
the four locks reproduce a 7730-field body of committed measurement; the winner
is m7 and renders 47.7 degrees of hue clear of its nearest neighbour; the
comeback claim the brief offered was tested and replaced with the one two
instruments agree on; every mark's placement was measured against this film's
own frames and every one of them is proven not to cover a racer; the film is
1150 contiguous frames with no duplicate, no black frame and no omission; and
the audio lands on the production reference.

Nothing here should be developed further. If Race #2 gets another pass, it
belongs in pacing — §13.4 and §13.5 are both the same complaint about the same
four seconds — and that would re-open the camera and the course, which is a
different brief from this one.
