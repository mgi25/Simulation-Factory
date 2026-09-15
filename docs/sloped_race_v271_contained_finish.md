# V27.1 — the finish correction

V27 recommended `contained_hall` at 55 of 60 and left one number open: the
machine-to-background separation at the winner fell from V26's 90 luma to 49,
and at the payoff from 84 to 53. This pass closes it. The headline is at §2 and
it is not the one the brief expected, so §3 is the evidence for it before
anything is changed.

    branch     v271-contained-hall-finish
    base       origin/v27-contained-environment-lab @ 31f8c05
    profile    contained_hall_v271
    seed       5432, untouched
    delta      one field: the finish bay's landing pad, hall_deck -> hall_deck_dark

Nothing about the physics, the replay, the camera solve, the edit, the hook,
the payoff, the audio, the meridian rotation, the machine palette, the hall's
architecture, its wall radius, its deck structure, its obstacle treatment, its
fork portal or its runtime is touched.

---

## 1  What was asked, and what was found

The brief's premise is V27's §19.1: *"A's machine-to-background at the winner
is 49 luma against V26's 90. The cause is V24's own finish practical now
landing on a wall."*

Two findings, in the order they were reached.

**The lamp is not the cause, and at the two payoff moments the wall is not the
problem either.** At the winner the hall's enclosure band measures 17.0 luma
against V26's 26.4, and at the payoff 11.4 against 37.8: the wall behind the
finish is *darker* than the rock it replaced in both of the shots V27's §19
quoted. It is brighter at the final approach — 45.4 against 6.9 — and that is a
real residual, named at §12.2, but it is the lower wall at radius 92 rather
than anything the finish practical lands on, and it is not where the 90-to-49
number came from.

**Most of the 90-to-49 drop is the ruler.** V27's segmentation counts the
cream finish chute — the brightest machine surface in the frame — as background
in the contained case and as machine in the control. Corrected, the same
frames read 96.4 against V26's 90.9 at the winner and 100.1 against 85.3 at the
payoff. §3.

**One real loss remains, and it is one object.** At the final approach the
hall stands 112.0 against V26's 128.4, and 27.8 per cent of that frame is the
finish bay's own landing pad at luma 51, against V26's 20-luma ravine floor.
§4.

---

## 2  The correction

```
contained_hall_v271 = contained_hall
    world.deck.pads[0].material   hall_deck -> hall_deck_dark
```

One field. No geometry added, no material key that the hall did not already
have, no light, no grade, no sky, no fog, no camera, no timing.
`tests/test_sloped_v271_contained.py::test_the_delta_is_exactly_one_leaf`
resolves both profiles, diffs every leaf and fails on a second difference.

`contained_hall` itself is **not** overwritten. Every proof in
`docs/sloped_race_v27_contained.md` still reproduces from the profile that
produced it, and the suite renders a V27 frame twice and compares hashes to say
so.

### What it does

    machine-to-background separation, luma, corrected instrument

    moment              V26      V27    V27.1     against V26   against V27
    final approach    128.4    112.0    121.2         -7.2          +9.2
    winner             90.9     96.4     99.0        +8.1          +2.6
    payoff             85.3    100.1    101.3       +16.0          +1.2

Target was 70, ideal 75–85. All three clear it, two of the three are above the
control, and the third closes 56 per cent of its gap to the control.

At the silhouette — the outer six pixels of the machine against the twelve
pixels of world outside it, measured on the machine **both** worlds show:

    moment              V26      V27    V27.1
    final approach     96.7     93.1    102.4
    winner             78.7     84.7     88.9
    payoff             64.1     87.3     90.5

---

## 3  The instrument, and why V27's number was not a like-for-like one

`v27_contained.segment` splits a marker render into four depth bands by nearest
hue, and subtracts the machine by requiring the **whole** marker pass and the
**world-only** pass to agree at a pixel. The intent is exact: a pixel the
machine covers shows the machine in one and the world in the other, the two
disagree, and it is dropped.

It fails when the machine's own colour lands in the same nearest-hue bucket as
the world behind it. The finish chute is warm cream, around (230, 222, 190).
Its distances to V27's four band hues are

    terrain   (255,  60, 120)   178      <- nearest
    structure (255,   0, 200)   224
    deck      (255, 120,   0)   217
    shell     (  0, 230, 160)   232

Cream is not pink. Rose is simply the least distant of four saturated hues, none
of which is cream — which is all "nearest hue" asks. So:

* in `contained_hall`, the chute stands over the repainted landform, which the
  marker paints rose. **Both passes say terrain.** The brightest machine surface
  in the frame is counted as background *and* removed from the machine, which
  moves the measurement twice in the same direction.
* in `aurora_valley_v26`, the same chute stands over V26's near-field rock,
  which the control marker paints magenta. The passes disagree and the chute is
  correctly discarded.

The error is therefore not noise; it is **asymmetric, and in the direction that
flatters the control**. At the winner it moves the hall's background mean from
31.6 to 61.7 and its machine mean from 128.0 to 111.0.

### The replacement

`v271_finish.machine_mask` asks the question the agreement test was
approximating: a pixel is machine where **removing the machine changes it**.

    machine = |whole - world|.max(channel) > 24

It is exact here and would not be on a lit render: every material a marker
profile paints is `unshaded` and `no_fog`, so a world surface is the same
constant colour in both passes — no shading to change, no shadow from the
object that was removed, no fog. The only thing that can differ is which object
a pixel is.

The threshold is on a plateau, not a knife edge. At the winner,
`contained_hall`'s machine cover is 49.9% at a floor of 4, 47.8% at 12, 46.8%
at 24 and 46.4% at 48, because the two populations being separated are
"unchanged flat colour" and "a different object entirely".

### What it changes, and what it does not

    winner crossing            V26      V27
    V27's instrument          90.1     49.3     the published pair
    corrected                 90.9     96.4

The control barely moves — 90.1 to 90.9 — which is the check on the correction:
where the two instruments cannot disagree, they do not.

`--stage measure` prints both, always, side by side. V27's numbers are not
withdrawn; they are explained.

---

## 3.1  A second instrument error, mine, and how it was caught

The first surface probe painted `hall_trim` **white**, found 2 to 8 per cent of
every frame at luma 245, and concluded that the hall's cornice was blowing out
and was the single biggest readability defect in the pass. It then survived four
render trials of raising the trim's roughness and dropping its specular, none
of which moved the number by 0.01 — which is what said the number was not about
the trim.

White is the machine's own pearl and the finish chute's cream. The classifier
had been handed the one hue the machine also wears. **Nothing the hall builds
clips white at any moment** — `surfaces.txt`'s last column is 0.00% on every
row — and the hall's 1.05% mean white clipping is the machine's, as V26's 1.04%
is.

`v271_finish.surface_masks` now takes the machine mask as an argument and
subtracts it before classifying, and `SURFACES` carries the finding beside the
table it caused.

Both errors are the same error: a mask built from colour, in a picture where
two different things are the same colour.

---

## 4  What is actually behind the finish

`--stage survey` reads the solved track with the film's own projector and asks
which pieces of the hall the three finish cameras see.

    part           pieces  at finish finish only never seen
    shell 0            32          7          0         16
    shell 1            32          0          0         31
    shell 2            24          6          0         12
    shell 3             6          0          0          4
    deck 0             28          6          0         16
    deck 1             32          7          0         17

**Not one piece of wall or deck is private to the finish.** Every segment the
winner camera sees is also in the obstacle, the branch or the merge. The
brief's preferred fixes 1, 3 and 6 — a darker background behind FINISH, a lower
wall value behind it, a repositioned architectural frame — have no shared-free
surface to act on. What is local to the finish is the bay's own furniture,
sited at the finish node and built nowhere else.

So the question becomes: which of the bay's own forms is the bright one.

`--stage surfaces` paints every hall material its own flat hue and reads the
lit frame through it, with the machine subtracted:

    final approach     cover      V27    V27.1
    hall_panel_dark   15.49%     44.9     44.9
    hall_rib           2.60%     47.3     47.1
    FINISH PAD        27.82%     50.7     25.0
    landform           3.01%     38.6     38.6

    winner             cover      V27    V27.1
    hall_panel_dark   14.55%     16.2     16.2
    FINISH PAD         6.39%     44.6     23.2

    payoff             cover      V27    V27.1
    hall_panel_dark   32.42%     11.2     11.2
    FINISH PAD         3.37%     46.9     24.0

The pad is `hall_deck`, and so is the radius 88–124 deck ring, so a probe that
gives the material one hue cannot say which of the two is in shot.
`_probe_v271_pad` re-materials the pad alone, and the answer is unambiguous: of
the 28.55 points of `hall_deck` in the final-approach frame, **27.83 are the
pad**; at the winner, 6.39 of 6.41; at the payoff, 3.38 of 3.46. The deck ring
is very nearly not at the finish at all.

The pad is a 40 × 34 slab laid under the line, and V27 §14 is right that it is
what gives the finish a place to stand. It was simply a value too light for
what stands on it.

---

## 5  Where the delta lands

    moment             changed px   max dLuma   mean dLuma
    frame0                 0.000%         0.0         0.00
    mixer                  0.000%         0.0         0.00
    release                0.000%         0.0         0.00
    descent                0.000%         0.0         0.00
    obstacle               2.587%        32.3        18.06
    fork_approach          0.030%        31.5        28.03
    split                  0.657%        27.2        24.66
    branch                 7.844%        33.5        20.37
    merge                  7.669%        32.1        24.51
    final_approach        28.886%        40.9        25.76
    winner                 6.463%        37.0        21.37
    payoff                 3.495%        37.9        22.92

**The delta is not confined to three frames, and no choice of surface could
have confined it.** The pad stands behind the finish and eight of the twelve
cameras see some of it — the merge moment's own description in
`v27_contained.MOMENTS` is "the routes rejoining, with the finish already in
frame", and the branch looks down the same line.

This is a deviation from the brief's "finish-specific delta only" and it is
stated rather than hidden. What can be shown is that it costs nothing: the
correction **improves every frame it reaches and regresses none**.

    moment              V26      V27    V27.1
    frame0            119.5    117.0    117.0
    mixer             107.1    114.0    114.0
    release           120.3    124.7    124.7
    descent           135.0    131.0    131.0
    obstacle          106.2    107.8    108.8
    fork_approach     103.2     97.1     97.1
    split             111.6    103.3    103.5
    branch            116.3    107.6    109.6
    merge             120.3     95.9     98.3
    final_approach    128.4    112.0    121.2
    winner             90.9     96.4     99.0
    payoff             85.3    100.1    101.3

Black clipping moves by at most 0.08 points of a per cent at any moment; white
clipping does not move at all.

---

## 6  The winner, the ring and the payoff

**Through the finish** (`winner.txt`). Marble 5, PURPLE, projected from the
replay rather than read off a sheet — `readability.cut_reads` cannot answer
this, because it drops a racer the moment it crosses and the winner's ring
opens *on* the crossing.

    moment          world   on screen    px   occluded   dE surround
    final approach  v271          no      -          -             -
    winner          v271         yes     55       0.00         132.0
    payoff          v271         yes     46       0.00         125.4

    for comparison, V26:  winner 144.5, payoff 125.8

At the final approach the winner is genuinely not in shot — it projects to
x = 1437 in a 1080-wide frame and crosses 1.05 s later. Nothing stands in front
of it at either of the moments where it is: no hall column, no bay frame, no
pylon. Its colour distance from the picture around it is 132 at the winner
against V26's 144.5, and 125.4 at the payoff against 125.8 — a real but small
loss at one moment, on a figure where V24's own legibility bar is in the
twenties.

**The ring** (`ring.txt`). V24 opens the WINNER mark on the crossing and runs
it 0.300 s. Measured by V26's own method — project the winner at each of the
eighteen frames and read back the rendered pixel:

    world   in frame   reads purple   median dE
    V26        18/18          12/18        48.0
    V27        18/18          12/18        50.1
    V27.1      18/18          12/18        50.1

Identical to the control. The mark is composited onto the proof board's third
row so it can be seen landing.

**The payoff** (`payoff.txt`). V24's card, unchanged, measured with
`v24_payoff.measured_contrast` on each world's own payoff frame:

    world   worst   median   band max
    V26      7.79    16.25       78.1
    V27     14.18    19.25       40.0
    V27.1   14.18    19.25       40.0

The card reads **better** on the contained bay than on V26's — 14.18 against
7.79 at the worst glyph — because the band it lives in tops out at 40 luma
instead of 78. The brief's bar was "at least V26's"; this is 1.8 times it.

**Frame zero** (`hook.txt`). Byte-identical to `contained_hall`, and therefore
to V27's published table:

    world   racers   worst column    mean   plate   least racer dE
    V26        8/8           8.64   15.21    30.4             65.9
    V27.1      8/8           8.45   15.41    30.3             71.7

Eight of eight racers legible, PICK A COLOR at 8.45 against a WCAG bar of 3.0,
and no bright distraction introduced anywhere in the opening. The correction
does not reach the hook, the mixer, the release or the descent at all.

---

## 7  The country-skin probe

Render-only, and one marble of eight. `racer_visual.gd` gains one appearance,
`flag_in`, reachable only through `--flag-racer=N`; with that option unset
nothing in the file behaves differently. There is no country system: no table
of nations, no per-racer assignment, no selection logic.

**India**, because it asks the two hard questions at once. A graphite hall has
very little white in it and a cream chute has a great deal, so a flag with a
white band tests separation from the background and from the machine in the
same frame; and the Ashoka Chakra is the smallest mark any skin in this family
would ever have to hold at 270 px wide.

It is the *same mechanism as the meridian marker*, which is what makes it
honest: the flag is baked into the racer's own albedo map, in the mesh's local
UV space, so it is carried by the replay quaternion exactly. Nothing reads
velocity, nothing holds a clock, and there is no path by which the skin could
invent a spin the solver did not produce. `racer_visual.gd`'s own header
predicted this build — "set `albedo_color` to white, bake the flag into the
image" — and that is what it is.

Three equal-area zones about a tilted axis, with the wheel on an axis
orthogonal to it, so the wheel sits in the middle of the white band and no
single rotation holds both the stripes and the wheel still.

    moment          world     px   dE around   bands seen   luma spread
    frame 0         v271     167       167.5          2/3           241
    frame 0         v26      167       167.7          2/3           239
    mixer           v271      78        64.0          2/3           179
    mixer           v26       78        65.9          2/3           180
    obstacle        v271      69        79.5          3/3           184
    obstacle        v26       69        83.1          3/3           178
    fork approach   v271      69        71.0          3/3           248
    fork approach   v26       69        72.3          3/3           248
    winner          v271      55        83.8          2/3           126
    winner          v26       55        82.4          2/3           113

**The hall is neutral to it.** Every row is within 4 of the control, and at the
winner the contained frame is *ahead*. A flag reads as a flag at every moment
sampled: two of three bands at frame 0, the mixer and the winner, all three at
the obstacle and the fork.

**Rotation reads.** The luma spread inside the marble's own patch is 126 to 248
of 255 at every moment, which is what a turning tricolour has and a solid
marble does not. The wheel resolves as 24 spokes at frame 0 (167 px) and as a
navy disc by the winner (55 px) — expected, and the honest limit of the
mechanism rather than of the room.

**Where it is tightest.** At the winner the white band sits against the cream
chute, which is the one collision this flag was chosen to find. The measured
distance is still 83.8, and the saffron and green carry the read.

`docs/validation/sloped_race_v1/v271_contained/country.png` is the five
moments, both worlds, with a 270 × 480 column.

---

## 8  Phone review

`phone.png` is the three finish moments at 270 × 480, and `proof.png` carries a
phone column of its own.

* **Final approach** — the clearest of the three. V26 is teal rock edge to
  edge; V27 puts a wide mid-blue floor behind the checkerboard; V27.1 takes
  that floor down and the board and the chute come forward. This is the frame
  the correction was made for and it is the frame it shows in.
* **Winner** — a small difference at this size. The wedge behind the gantry is
  darker; the marble and the FINISH board are unchanged.
* **Payoff** — nearly indistinguishable from V27, which is correct: the pad is
  3.4% of that frame. What the contained stage already won there — a 40-luma
  band instead of V26's 78 — it keeps.

At 270 px wide the contained finish is the quietest of the three and the
machine is the brightest thing in it at all three moments.

---

## 9  Performance

Four runs of the twelve moments per world, median of the engine's own
per-frame figure:

    world                  ms/frame (4 runs)    median
    aurora_valley_v26      322 322 327 321       322.0
    contained_hall         357 358 362 359       358.5
    contained_hall_v271    364 348 369 350       357.0

    V27.1 against contained_hall   -0.42%
    contained_hall against V26    +11.3%

The correction is free, as it must be: mesh instances (1513) and triangles
(540,440) are identical, and a material value does not cost a shader anything.
The −0.42% is inside the run-to-run spread, which is ±3% on this machine. The
brief's ±2% is met.

The hall's cost against V26 measures +11.3% here against V27's reported +7%;
the ratio is machine-dependent and the conclusion is V27's unchanged — these
frames are shading-bound, and a contained stage trades many small distant
objects for a few very large near ones.

---

## 10  Proofs

    docs/validation/sloped_race_v1/v271_contained/
        proof.png       the brief's five finish frames, three worlds,
                        plus a 270x480 column. The ring row has V24's own
                        mark composited onto it.
        finish.png      merge and the three finish moments, three worlds
        elsewhere.png   frame 0, the obstacle and the branch
        phone.png       the three finish moments at 270 x 480
        country.png     the India skin at five moments, two worlds, plus phone
        measures.txt    separation at all twelve moments, through both
                        instruments, plus the silhouette pairing and the
                        band tables
        surfaces.txt    what is behind the finish, by material
        survey.txt      which pieces of the hall the finish cameras see
        delta.txt       which frames the one-field delta reaches
        winner.txt      the purple racer through the finish
        ring.txt        the WINNER mark, frame by frame
        payoff.txt      the card's contrast on each world's payoff frame
        hook.txt        frame zero, unchanged
        country.txt     the flag probe's numbers

    exports/v271_contained_hall_finish/
        the boards and the texts above, plus
        finish_v26.mp4  finish_v27.mp4  finish_v271.mp4
        and a _phone.mp4 of each: the whole final cut, 15.567 to 20.117,
        273 frames, in all three worlds at 1080x1920 and 270x480.

---

## 11  Tests

`tests/test_sloped_v271_contained.py`, 41 assertions, all passing, of which 4
are Godot-gated and skip without `$GODOT_BIN`.

    the profiles resolve, are indexed, and the generator is a no-op
    contained_hall is not overwritten and no frozen profile names V27.1
    the delta is exactly one leaf, and it is the pad's material
    the delta adds no geometry, no material key, no light, grade, sky or fog
    the pad's size, place, bearing and guards are unchanged
    the seed, the moments, the frame size and the fps are V27's
    the lab renders V24's fixed flags and writes no input
    the track is read on its own clock, and every moment resolves on it
    machine_mask is an occlusion test with a threshold on the plateau
    V27's segmentation keeps the chute and the correction drops it
       - the 90-to-49 bug, reproduced in eight by eight pixels
    collar_pair uses the shared silhouette
    the flag key is an appearance Godot knows
    the lab fails on a scene push_error rather than photographing it
    the shipped appearances and the marker's own constants are untouched
    a flag reaches only the chosen racer, and the default reaches none
    the flag axes are orthogonal and the bands are equal by area
    the payoff card is not redesigned, and reads at least as well as V26's
    the finish clears the brief's target at all three moments
    the correction regresses no moment
    the cost is within two per cent, with identical mesh and triangle counts
    frame 0, the mixer, the release and the descent are byte-identical
    the winner is on screen and unoccluded when it crosses
    the country probe actually rendered a flag
    [godot] V26 and contained_hall still render what they rendered
    [godot] the correction changes the winner and not the hook
    [godot] the correction builds the same world census as contained_hall
    [godot] the flag reaches one racer, and no default render reaches it

The wider suite is unaffected: 2901 passed, 186 skipped. One pre-existing
failure in `tests/test_neon_proof.py` reproduces identically on the untouched
V27 worktree and is unrelated to environments.

---

## 12  Weaknesses

1. **The delta is not finish-local, and cannot be.** §5. Eight of twelve
   moments see the pad. Every one of them improves, but the brief asked for
   three and got eight.
2. **The final approach is still 7.2 luma under V26.** The remaining gap is the
   lower wall at radius 92 (15.5% of that frame at luma 44.9) and it is shared
   with the obstacle and the split, so closing it is a hall change rather than a
   finish change and was not made.
3. **The merge is now the weakest moment in the film**, at 98.3 against V26's
   120.3 — a 22-luma gap, the largest of the twelve, and three times the finish's.
   It is outside this pass's scope and it is where a V27.2 should start.
4. **The winner's colour separation is 12.5 lower than V26's at the crossing**
   (132.0 against 144.5). Comfortable in absolute terms, but it is a real
   direction and it comes from the hall's darker surround rather than from
   anything this pass did.
5. **The country probe is one flag on one racer.** It answers "would a neutral
   stage host a flag" and nothing about eight flags at once, about flags that
   share a palette with each other, or about a flag against the start bay's own
   backboard, which V24's hook lab already found `sightlines` is blind to.
6. **Two instrument errors in one pass**, §3 and §3.1, both of them a mask
   built from colour in a picture where two things are the same colour. The
   corrected instrument is a difference rather than a classification and is not
   subject to that failure, but the *band* assignment inside it still is.
7. **`hall_deck` now paints only the deck ring at the finish**, which means the
   pad and the floor beyond it are one value there. It reads as a recess rather
   than a landing; whether that is the right architecture for a finish is a
   judgement the boards are for.

---

## 13  Is it ready to replace V26 outdoor in production?

**Yes, on the evidence here, with one reservation that is not the finish.**

What is settled:

* the finish is no longer the objection. Two of three finish moments are above
  the control and the third clears the brief's target by 51 luma; at the
  silhouette all three are above it;
* the payoff card reads nearly twice as well as it does on V26;
* the hook is byte-identical to V27's, which was byte-identical to the
  measurement V27 published;
* the ring lands exactly as it does on V26, frame for frame;
* a country skin is readable in it, and no less readable than in V26;
* it costs 34 per cent fewer mesh instances and 17 per cent fewer triangles
  than V26 for 11 per cent more frame time, and nothing over `contained_hall`.

The reservation is §12.3: the **merge** is 22 luma behind the control, which is
a bigger gap than the finish ever had, in a cut the film spends 0.48 s in. It
was not in this brief's scope and it should be closed before the hall ships, by
the same method this pass used — name the surface, then change its value.

The integration itself remains what V27 §20 described: `sloped/v27.py` is
`sloped/v26.py` with `ENVIRONMENT = "contained_hall_v271"`, and one edition row
borrowing V24's solved track.

---

## Files

    sloped/v271_finish.py                        the corrected instrument
    tools/sloped_v271_profiles.py                writes the four profiles
    tools/sloped_v271_finish.py                  renders, measures, reports
    godot/.../racers/racer_visual.gd             +1 appearance (render-only)
    godot/scripts/sloped_race_scene.gd           +--flag-racer
    godot/.../environment/profiles/              contained_hall_v271,
                                                 _marker_v271, _probe_v271,
                                                 _probe_v271_pad
    tests/test_sloped_v271_contained.py          41 assertions
    docs/validation/sloped_race_v1/v271_contained/   the boards and the tables
    exports/v271_contained_hall_finish/              the boards and the clips
