# V27.2 — the merge correction

V27.1 closed the finish and its §12.3 named what it left open: *"the merge is
now the weakest moment in the film, at 98.3 against V26's 120.3 — a 22-luma
gap, the largest of the twelve, and three times the finish's. It is where a
V27.2 should start."* This is that pass.

    branch     v272-contained-hall-merge
    base       v271-contained-hall-finish @ b299581
    profile    contained_hall_v272
    seed       5432, untouched
    delta      one leaf: hall_panel_dark's specular, 0.5 (a default) -> 0.06

Nothing about the physics, the replay, the seed, the course, the camera solve,
the edit, the timing, the hook, the payoff, the audio, the racers, the hall's
architecture, V27.1's finish bay fix, the finish pad material, the obstacle,
the fork or the country probe is touched.

The headline is at §2. It has two halves and the second one is not the half the
brief expected, so §3 is the evidence before anything is changed.

---

## 1  What was asked, and what was found

Three findings, in the order they were reached.

**The bright thing at the merge is one material, and it is not the one the
survey pointed at.** `hall_panel_dark` is 28.5 per cent of the merge background
at luma 47.7, against a landform at 25.5 — the merge bay's own backing slab
(15.5% of the frame) and the lower wall at radius 92 (5.7%), which share the
key. Eight candidate objects were probed one at a time; the other six are not
in the shot at all. §4.

**It is not bright because of its value. It is bright because of a specular
lobe.** A *black, un-emissive, un-backlit, un-fogged* `hall_panel_dark` still
renders at 31.2 of its 46.0 luma at the merge. `lab_palette._matte` sets
albedo, metallic and roughness and never touches `metallic_specular`, so the
material has been running at `StandardMaterial3D`'s default 0.5 since V27, and
at roughness 0.88 that lobe is broad enough to take an even sheen from all five
of the rig's directional lights at once. Cutting the albedo by 56 per cent
moves the surface 6 luma; cutting the specular moves it 32. §5.

**Most of the 22-luma headline was never contrast.** Measured on the pixels
both worlds actually show, V26's advantage at the merge is 8.5 luma, not 22.0.
The other 13.5 is V26's foreground rock standing in front of the machine and
hiding its far, dark, lower edge, which lifts V26's *visible*-machine mean and
is not a property of either background. §3. This is the same class of finding
as V27.1 §3, found with V27.1's own instrument, and it is why the brief's
"≥110" is met on a like-for-like footing and missed by 2.3 on a whole-frame
mean.

---

## 2  The correction

```
contained_hall_v272 = contained_hall_v271
    palette.hall_panel_dark.specular   <absent, running at 0.5>  ->  0.06
```

One leaf, and it is a leaf **no profile had ever named** — which is why no
earlier pass had a field to look at. No geometry, no new material key, no value
change, no light, no grade, no sky, no fog, no camera, no timing.
`tests/test_sloped_v272_contained.py::test_the_delta_is_exactly_one_leaf`
resolves both profiles, diffs every leaf and fails on a second difference.

`contained_hall` and `contained_hall_v271` are **not** overwritten. Every proof
in `docs/sloped_race_v27_contained.md` and
`docs/sloped_race_v271_contained_finish.md` still reproduces from the profile
that produced it, and the suite renders a frame of each and compares hashes to
say so.

### What it does

    machine-to-background separation, luma, V27.1's instrument, list A

    moment              V26     V27.1    V27.2     against V26   against V27.1
    frame0            119.5    117.0    117.0          -2.4          0.00
    mixer             107.1    114.0    114.7       over V26         +0.69
    release           120.3    124.7    124.7       over V26         +0.05
    descent           135.0    131.0    132.6          -2.4          +1.57
    obstacle          106.2    108.8    110.9       over V26         +2.10
    fork_approach     103.2     97.1     98.7          -4.5          +1.63
    split             111.6    103.5    105.4          -6.2          +1.92
    branch            116.3    109.6    113.4          -2.9          +3.79
    merge             120.3     98.3    107.7         -12.5          +9.41  *
    final_approach    128.4    121.2    127.8          -0.6          +6.60
    winner             90.9     99.0    101.3       over V26         +2.30
    payoff             85.3    101.3    103.7       over V26         +18.4

    * the moment the pass exists for.

**Every moment improves or is byte-identical, and none regresses.** The worst
step at any guarded moment is +0.00. Four moments are now above the control
that were not, and the final approach — V27.1's own remaining residual, its
§12.2 — closes from −7.2 to −0.6 without the finish being reopened, because the
lower wall it named is the same surface with the same defect.

The three merge frames, on their own `--at` list:

    moment              V26     V27.1    V27.2
    merge_approach    121.2    102.5    110.2
    merge             120.3     98.3    107.7
    post_merge        127.3    109.2    119.6

And at the silhouette — the outer six pixels of the machine against the twelve
pixels of world outside it, measured on the machine **both** worlds show:

    moment              V26     V27.1    V27.2
    merge_approach     80.4     84.2     85.1
    merge              78.7     85.6     86.6
    post_merge         74.0     83.2     83.2

---

## 3  Contrast, or coverage: what the 22 luma actually was

`separation` is a mean over the machine minus a mean over the background, and
each world supplies its own two populations. That is the right question about
one picture and the wrong one for a comparison, because **the two worlds do not
show the same machine.** V26's foreground rock stands in front of the course and
hides 3.8 per cent of the frame's worth of it, and what it hides is the far,
dark, lower edge — so V26's remaining silhouette is its bright half.

`--stage coverage` splits the gap four ways. Measured on V27.1 against V26,
before the correction:

    moment            dSep   dMachine  dBackgnd   dMach_same  dBackg_same
    merge_approach  -18.78     -9.25     +9.53        +0.10       +10.01
    merge           -21.96    -14.86     +7.10        -0.76        +7.75
    post_merge      -18.16    -12.67     +5.49        -0.02        +5.98
    final_approach   -7.22     -3.19     +4.03        -0.32        +4.44

`dMach_same` is the machine term measured on the pixels both worlds show, and
it is **zero to within 0.8 luma at every moment**. The hall does not darken the
machine at all. The large negative `dMachine` beside it is the occluder, not
the room.

`dBackg_same` is the real defect, entirely a background one, and it is what the
correction acts on.

Asked as a like-for-like question — one machine mask, one background mask, both
worlds read over them — the same frames give:

    separation on the pixels both worlds show

    moment              V26     V27.1    V27.2
    merge_approach    122.7    112.8    120.5
    merge             122.2    113.8    123.2
    post_merge        128.7    122.7    133.1
    final_approach    129.0    124.3    130.8
    winner             89.6     99.0    101.3
    payoff             85.7    103.1    105.5

On that footing V27.2 clears the brief's 110 at all three merge moments and is
**above the control at five of the six proof frames**. This is the pairing
V27.1 built `collar_pair` for, applied to the whole frame rather than to the
silhouette; it is not a new metric invented to flatter a result, and the
uncorrected number is printed beside it everywhere.

**The brief's ≥110 is therefore met on the like-for-like measure and missed by
2.3 luma on the whole-frame one at the merge moment itself.** §11.1 is the
arithmetic for why no local material change reaches 110 on the whole-frame
measure, and why reaching it would mean a black room.

---

## 4  Which object, and the probe that named it

`--stage survey` reads the solved track with the film's own projector. Unlike
the finish, the merge **does** have private architecture — 7 of the 22 pieces
its three cameras see are seen by no other camera — so a merge-local repaint was
available in principle. It was not needed, because the objects that matter are
not wall segments.

`--stage isolate` renders one probe per candidate, each re-materialling exactly
one object to `hall_grate` — the one key in `lab_palette`'s hall family that
`contained_hall` builds nothing from — and finds the object by **differencing
that probe against the base probe**. Measured on `contained_hall_v271`:

    object                       cover   luma   lever  headroom   gain

    the merge bay's backing     13.91%   46.1   0.194     +12.2   2.35
    the lower wall, radius 92    6.12%   49.1   0.084     +15.3   1.56
    the finish landing pad       8.77%   29.7   0.117      -4.2  -0.52
    deck ring 0, radius 88-124   0.00%      -   0.000         -   0.00
    deck ring 1, radius 122-154  0.00%      -   0.000         -   0.00
    the main drum, radius 122    0.00%      -   0.000         -   0.00
    the near wall, radius 90     0.00%      -   0.000         -   0.00
    the fork portal's wings      0.00%      -   0.000         -   0.00

`lever` is the object's share of the background: the luma of separation one
luma of darkening it would buy. Five of the eight candidates are not in a merge
frame at all, and the finish pad — V27.1's own correction — is now *darker*
than the background it sits in and is holding the number up rather than down.

The two that remain wear the same material, which is why a material probe could
not have settled it and an object probe had to. The material table agrees
exactly: `hall_panel_dark` is 21.06% of the merge frame, and the two isolates
are 21.21% of it between them.

### 4.1  The probe measured nothing, twice, before it measured this

The first version of this stage classified the probe by nearest hue, the way
V27.1's material probe does, and reported **0.00% cover for all eight
objects** — a clean, confident, finished-looking table of zeroes. The probe was
working perfectly. The isolate hue is authored `#00FF80` and renders
`(127, 243, 154)`: flat and stable, and 130 units from where the classifier had
been told to look, because an unshaded albedo still goes through the profile's
own grade.

The hue is now not used at all. An isolate probe differs from the base probe in
exactly one material, so the object is **where the two probes disagree** — the
same occlusion argument `v271.machine_mask` makes, exact for the same reason.
The hue was also moved from `#00FF80` to `#00A0A0`, 114 units clear of every
neighbour instead of 64 from `hall_panel`'s, so that a future reader who does
reach for it is not handed the trap; and it is deliberately not white, which is
the most distant choice on paper and is the machine's own pearl.

That is the third time in three passes that a mask built from colour has been
wrong in a picture where the colour was not what it was authored as. V27.1's
own conclusion — *"both errors are the same error"* — now has a third instance,
and the fix each time is to stop classifying and start differencing.

**A second instrument error, also mine.** The first version of the mechanism
table read V26's pixels through the *hall's* masks and printed 104.8 for a
frame that measures 120.3. Caught because it disagreed with `--stage measure`
on a number both should agree on, which is the only reason a report carries the
same figure in two places.

---

## 5  Why the surface is bright

`--stage mechanism` moves one field of `hall_panel_dark` at a time. Read on the
merge bay's backing slab, at the merge:

    the surface as authored                      46.0 luma
    with its albedo taken to black               36.7
    with its emissive floor off                  41.1
    black, un-emissive and un-backlit            31.2
    the same with fog disabled                   31.3
    as authored, with specular 0.06              14.4

A black, un-emissive, un-backlit, un-fogged surface still reads 31.2. It is not
value, not `floor_lift`'s emission, not `soft_light`'s backlight and not fog —
disabling fog moves it by a tenth of a luma, which is the measurement that
killed the obvious answer.

It is a **specular lobe**, and the delta is a reflectance rather than a value.

### 5.1  It is a lift, not a highlight

This is the whole justification for removing it. The slab's own 5th-to-95th
percentile spread is **2.6 luma with the lobe and 0.9 without it** — the lobe
is an even sheen laid across the surface, not a gradient that describes its
form. Nothing that models the wall is being taken away.

`hall_rib` on the same frame is 4.92% of the picture at 58.5 luma with a spread
of **27.4**. *That* lobe is a highlight — the vertical band
`environment_stage._shell_rib` exists so a viewer can read the wall's height
off — and `hall_rib` keeps its specular. The distinction between the two is the
reason this pass changes one material and not the family.

### 5.2  Why 0.06 and not 0.00

    specular   merge_approach   merge   post_merge   backing luma
    0.00                110.3   108.0        119.9           13.6
    0.06                110.2   107.7        119.6           14.4   <- ships
    0.12                109.8   107.3        119.1           15.9
    0.20                108.9   106.2        118.0           19.6
    0.30                107.3   104.2        115.7           26.3
    0.50 (V27.1)        102.5    98.3        109.2           46.0

Zero is available and costs 0.3 luma more of separation. It is not taken,
because the palette's own stated requirement is a stage *"meant to outlive this
racer palette, this machine colour language and this course"*, and a surface
with no reflectance at all is inert under any future rig rather than merely
quiet under this one. 0.06 is a reduction; 0.00 is an ablation. `mechanism.png`
is the ladder as pictures, because the value was looked at and not only
measured.

---

## 6  Where the delta lands

    moment             changed px   max dLuma   mean dLuma   dSeparation
    frame0                 0.000%         0.0         0.00        +0.00
    mixer                  2.328%        46.8        20.40        +0.69
    release                0.164%        17.7        15.84        +0.05
    descent                4.984%        48.6        21.88        +1.57
    obstacle               3.975%        48.9        21.79        +2.10
    fork_approach          9.655%        41.6        12.83        +1.63
    split                 15.461%        48.3        10.12        +1.92
    branch                22.090%        48.8        13.31        +3.79
    merge                 21.177%        37.4        32.91        +9.41
    final_approach        15.547%        33.4        30.96        +6.60
    winner                13.637%        27.0         8.86        +2.30
    payoff                26.086%        47.5         4.93        +2.32

**The delta is not merge-local, and a material-level change could not be.**
`hall_panel_dark` is the lower wall as well as the merge backing, and eleven of
the twelve moments see some of it. This is a deviation from the brief's "smallest
possible local change" read strictly as "local in the frame", and it is stated
rather than hidden.

What can be shown is that the separation **improves at every frame it reaches
and regresses at none**, by between +0.05 and +9.41 luma. Frame zero is
byte-identical and white clipping does not move at any moment by so much as a
ten-thousandth of a per cent.

The genuinely local alternative was built and measured — the merge backing
alone, reassigned to `hall_grate` and given the same treatment, which reaches
no other frame in the film. It buys +1.6 at the merge against this delta's
+9.4, because it leaves the lower wall at 52.6 luma. The narrower change is the
worse picture and the smaller correction, and it was not taken.

### 6.1  The black floor, which is the delta's one real cost

Black clipping does **not** stay still, and an earlier draft of this document
said it did. Taking a lobe off a surface that was already dark puts part of
that surface under luma 5:

    moment            region of frame   luma V27.1   luma V27.2   region <=5
    merge                      21.2%          45.7         14.0         0.0%
    final_approach             15.5%          45.0         14.0         0.0%
    obstacle                    4.0%          35.9         10.5         1.3%
    descent                     5.0%          33.7          9.9         0.3%
    fork_approach               9.7%          12.7          5.7        28.2%
    split                      15.5%          12.0          5.7        42.4%
    branch                     22.1%          12.7          7.5        31.3%

    whole-frame black clipping    V26     V27.1    V27.2
    fork_approach               2.15%     2.52%    5.58%
    split                       2.06%     2.58%    9.85%
    branch                      5.26%     3.03%   10.12%

Where the surface was bright it lands near 14 and nothing clips. Where it was
already dark — the fork family, at about 12 luma — it lands near 6 and a third
of it goes under the floor. **The moments that gain the most clip the least**,
which is the shape of the trade.

It is not a tuning error, and the ladder says so: at the branch, whole-frame
black clipping is 10.12% at specular 0.06, 10.02% at 0.12 and 9.78% at 0.20,
while the merge's gain falls from +9.41 to +7.90 over the same range. Specular
is not the dial for a black floor; `floor_lift` is, and turning it would lift
the merge back by the same constant. It was not turned.

**It is not a visual regression at the size that decides.** `fork_phone.png` is
the three fork frames at 270 × 480 in all three worlds, and V27.2 is not
distinguishable from V27.1 by eye: what changes is the depth of an
already-dark ground rather than the presence of detail, because the ribs, trim
and beams that carry the wall's form are other materials and are untouched —
they now read *against* a darker panel rather than with it. The separation at
all three fork moments improves.

It is still a change of character at three moments that the merge brief did not
ask for, and it is named again at §12.4.

---

## 7  The guards

**Frame zero** (`hook.txt`). Byte-identical to `contained_hall_v271`, and
therefore to V27.1's published table.

    world   racers   worst column    mean   plate   least racer dE
    V26        8/8           8.64   15.21    30.4             65.9
    V27.1      8/8           8.45   15.41    30.3             71.7
    V27.2      8/8           8.45   15.41    30.3             71.7

**The fork and the obstacle** (`regress.txt`). `obstacle` +2.10, `fork_approach`
+1.63, `split` +1.92, `branch` +3.79. All four gain; the obstacle is now above
the control.

**The finish** (`measures.txt`). Not reopened, and it does not fall:
`final_approach` +6.60, `winner` +2.30, `payoff` +2.32, all three still clear of
V27.1's own 70 bar by wide margins.

**The winner** (`winner.txt`). Unchanged at the crossing: 55 px, 0.00 occluded,
colour distance from its surround 132.0 — V27.1's own figure to the decimal.
At the payoff 46 px, 0.00 occluded, 125.4.

**The ring** (`ring.txt`). V24's schedule is untouched and this pass's clip is
the merge, 13.450 to 16.100, so the mark's own eighteen frames are not in it.
**No number for it is invented here.** V27.1 measured 12 of 18 frames reading
purple at a median dE of 50.1, identical to V26's 12 of 18 at 48.0, and what is
checked instead is that the frames the mark is drawn on are in the guarded
table.

**The payoff card** (`payoff.txt`). V24's card, unchanged, measured with
`v24_payoff.measured_contrast`:

    world   worst   median   band max
    V26      7.79    16.25       78.1
    V27.1   14.18    19.25       40.0
    V27.2   18.96    19.47       19.0

The worst glyph reads 2.4 times as well as it does on V26, and the band the
card lives in tops out at 19 luma instead of 78. The card is not redesigned.

**The country probe** (`country.txt`). Re-run, not expanded: the same one flag
on the same one racer through the same one appearance behind the same
`--flag-racer=`. Every row is **identical to V27.1's** — 167/78/69/69/55 px,
two or three bands seen, the same spreads, colour distances within 0.0. The
merge correction does not reach it.

---

## 8  The instrument

Stated once, because the brief asks for it explicitly.

* **machine** — `v271.machine_mask` on each world's own marker pair: a pixel
  where hiding the machine changes the marker render by more than 24/255 on any
  channel. An occlusion test, not a hue classification. Exact here because
  every marker material is `unshaded` and `no_fog`, so a world pixel is a
  constant colour between the two passes and the only thing that can differ is
  which object it is.
* **background** — the union of `v27.segment`'s four depth bands, minus that
  machine mask.
* **exclusions** — none. What belongs to neither population is the sky, which
  the marker does not paint.
* **common** — for §3, the intersection of the two worlds' machine masks and,
  separately, of their background masks.
* **why it is valid here** — it reproduces V27.1's entire published table from
  V27.1's own profiles, to within 0.1 luma at all twelve moments, before
  anything of this pass's is measured with it.

Two more things make the comparison exact rather than close:

**The ruler did not move.** The depth-band marker over `contained_hall_v272`
renders **byte-identically** to the marker over `contained_hall_v271` at every
frame of both lists — an unshaded surface has no specular response — so the two
worlds' separations are read through literally the same mask. Asserted as a
render, not argued.

**The two `--at` lists agree.** This pass renders four moments twice, once
inside the twelve V27 moments and once inside the brief's six, because V27
found that a still is only comparable with one asked for in the same list. The
measured cost of that duplication is **at most 0.01 luma of separation**, on at
most 0.05 per cent of pixels. That is the error bar on every cross-list
quotation in this report, and it is measured rather than assumed.

### 8.1  No probe artefact is left behind

V27.1 left four profiles in the registry, three of them diagnostics. This pass
leaves **one**, and it is the shipped profile.

The depth-band marker and all ten surface probes are written, rendered and
deleted inside `sloped_v272_profiles.temporary`, which restores `index.json`
from the bytes it had on entry rather than by removing the ids it added — so an
interrupted run cannot leave the file reordered — and refuses to write a
profile whose file already exists, so no exit path can delete a committed one.
`--stage clean` reports leftovers and the suite asserts there are none.

One cost of that arrangement is worth recording: a temporary profile is in the
registry for as long as it takes to render, and anything else reading the
registry in that window holds it to the same standard as a shipped profile. A
concurrent test run in this tree failed on a diagnostic's short `summary` while
it existed. The summaries are padded now, but the hazard is structural: **do
not run the lab and the suite against the same working tree at the same time.**

---

## 9  Performance

Four runs of the twelve-moment list per world, median of the engine's own
per-frame figure:

    world                  ms/frame (4 runs)    median
    aurora_valley_v26      338 337 349 328       337.5
    contained_hall_v271    356 363 343 356       356.0
    contained_hall_v272    350 351 351 362       351.0

    V27.2 against V27.1   -1.40%

Inside the brief's ±2%, and inside the run-to-run spread, which is about ±3% on
this machine. Mesh instances (1513) and triangles (540,440) are **identical**,
which is the claim that matters: the delta adds no draw call, no shader variant
and no vertex, so the honest expectation is zero and the −1.40% is noise.

---

## 10  Proofs

    docs/validation/sloped_race_v1/v272_contained/
        proof.png       the brief's six frames, three worlds
        merge.png       the three merge frames, three worlds
        elsewhere.png   the hook, the obstacle and the fork
        phone.png       the brief's six at 270 x 480
        mechanism.png   the specular ladder, as pictures
        country.png     the India skin at five moments, three worlds
        measures.txt    separation at every moment of both lists, plus the
                        silhouette pairing and the exposure tables
        coverage.txt    contrast against coverage: what the 22 luma was
        isolate.txt     which object is the bright one, by controlled probe
        mechanism.txt   why it is bright, field by field, and why 0.06
        surfaces.txt    the same frames by material, for the record
        survey.txt      which hall pieces the merge cameras see
        listcheck.txt   what the two --at lists cost
        delta.txt       which frames the one-leaf delta reaches
        regress.txt     the brief's guards in one table
        winner.txt      the purple racer through the merge and the finish
        payoff.txt      the card's contrast on each world's payoff frame
        hook.txt        frame zero, unchanged
        ring.txt        why no ring number is invented here
        country.txt     the flag probe's numbers
        timing.txt      four runs per world
        cost.txt        mesh, triangle and frame-time comparison

    exports/v272_contained_hall_merge/
        the boards and the texts above, plus
        merge_v26.mp4  merge_v271.mp4  merge_v272.mp4
        a _phone.mp4 of each at 270 x 480, and
        merge_compare.mp4, the three side by side

The clip is the brief's mandatory one: output 13.450 to 16.100, 159 frames —
the branches cut, the merge, and 0.53 s of the final cut, so the rejoin is
followed rather than cut away from. It opens 0.05 s after the branches boundary
rather than on it, because a frame on a cut boundary belongs to whichever of
two shots the renderer resolved first.

---

## 11  Phone review

`phone.png` is the brief's six frames at 270 × 480.

* **Merge approach** — the clearest of the three. V27.1 puts a wide flat teal
  plane across the upper right; V27.2 takes it down and the FINISH gantry, the
  cream chute and the two route rails come forward. The wall's vertical rib
  rhythm survives the change and is in fact easier to count against the darker
  ground.
* **Merge** — the same move, smaller. The machine is unambiguously the
  brightest thing in the frame at this size, which it was not before.
* **Post-merge** — the largest numerical gain (+10.4) and a visible one: the
  upper-left wall stops competing with the track.
* **Final approach, winner, payoff** — the finish is not reopened and does not
  change character; the payoff's background band is quieter than either
  predecessor's.

At 270 px wide the corrected hall is the quietest of the three worlds and the
machine is the brightest thing in every one of the six frames. Racer
readability is unchanged: the country probe's numbers are identical to V27.1's
at all five of its moments, and the hook's eight-of-eight is byte-identical.

---

## 11.1  Why ≥110 is not reachable on the whole-frame measure

The brief's target is quoted against the whole-frame mean, so the arithmetic is
worth stating plainly rather than leaving as an excuse.

Separation is `machine_mean − background_mean`, and §3 shows the machine term
is not available: on the pixels both worlds show, the hall's machine is within
0.8 luma of V26's. So every luma of the target has to come out of the
background, which stands at 35.7 at the merge against V26's 28.6.

Taking the whole merge background to V26's own value — every surface, including
the course's own landform — would give +7.1 and land at 105.4. Reaching 110
needs the background at 24.0, **darker than V26's outdoor night**, in a room
that is supposed to read as a premium machine hall. The delta actually achieves
+9.4 rather than +7.1 only because it also lifts the machine's own contrast
against what remains.

The brief also says to prioritise the actual picture over matching V26
numerically. On the like-for-like measure the corrected hall is at 123.2 at the
merge against the control's 122.2, and the pass stops there rather than
darkening the room to move a number whose remaining gap is an occluder.

---

## 12  Weaknesses

1. **The whole-frame merge number is 107.7, 2.3 under the brief's 110.** §11.1
   is why, and §3 is the measure on which it is 123.2. Both are printed
   everywhere; neither is withdrawn.
2. **The delta is not merge-local.** §6. Eleven of twelve moments see
   `hall_panel_dark`. Every one of them improves, but the brief asked for a
   local change and got a material-wide one. The genuinely local version was
   built, measured at +1.6 against +9.4, and rejected on the picture.
3. **The fork family clips black.** §6.1. At the split, 42 per cent of the
   changed region goes under luma 5, and whole-frame black clipping there goes
   from 2.58% to 9.85% against V26's 2.06%. Measured, not fixable with this
   field, invisible at 270 px, and still a real change of character at three
   moments the brief only asked me not to break. `floor_lift` is the dial that
   would answer it and turning it is a second leaf and a second pass.
4. **`hall_panel_dark`'s specular was a default, not a decision** — which means
   the same is true of every other `_matte` surface in the family, including
   `hall_deck`, `hall_deck_dark`, `hall_beam` and `hall_grate`. This pass
   changed the one the merge named and did not audit the rest. That audit is
   the obvious V27.3 and it was deliberately not done here.
5. **A third colour-mask instrument bug**, §4.1, plus a mask-mismatch bug of my
   own in the mechanism table, plus a false "clipping does not move" claim in
   an earlier draft of §6 that the delta stage's own numbers contradicted. All
   three were caught, all three are documented, and the surviving instruments
   are differences rather than classifications — but the band assignment
   *inside* the segmentation still classifies by hue.
6. **The fork is now the weakest moment in the film.** At 98.7 it has taken the
   place `merge` held at 98.3, and the merge at 107.7 is no longer an outlier.
   That is where a V27.3 would start, and §12.3 is probably its mechanism too.
7. **The country probe is still one flag on one racer**, exactly as V27.1 left
   it. This pass verified it did not move and deliberately did not extend it.
8. **The lab and the suite cannot share a working tree.** §8.1.

---

## 13  Is `contained_hall_v272` ready for production integration?

**Yes, on the evidence here.**

* the merge is corrected by +9.4 luma and is above the brief's target on the
  like-for-like measure at all three of its moments;
* the finish is not reopened and improves anyway, closing V27.1's own §12.2
  residual from −7.2 to −0.6 against the control;
* every one of the twelve moments improves or is byte-identical, and none
  regresses;
* frame zero is byte-identical, so the hook is provably untouched;
* the payoff card reads 2.4 times as well as it does on V26;
* the country skin reads exactly as it did in V27.1;
* it costs nothing: identical mesh and triangle counts, −1.40% frame time
  inside a ±3% spread;
* the registry gains one profile and no diagnostics.

The integration is what V27 §20 and V27.1 §13 described, with one name changed:
`sloped/v27.py` is `sloped/v26.py` with `ENVIRONMENT = "contained_hall_v272"`,
and one edition row borrowing V24's solved track.

The reservation is §12.3 rather than anything about the merge: the specular
default this pass found on `hall_panel_dark` is present on every other `_matte`
surface in the hall family, and nobody has looked at them. That is a known
unexamined lever, not a known defect.

---

## Files

    sloped/v272_merge.py                         the moments, the isolates, the
                                                 instrument re-exported
    tools/sloped_v272_profiles.py                writes one profile, lends ten
                                                 ephemeral diagnostics
    tools/sloped_v272_merge.py                   renders, measures, reports
    godot/.../environment/profiles/              contained_hall_v272 (one file)
    tests/test_sloped_v272_contained.py          70 assertions
    docs/validation/sloped_race_v1/v272_contained/   the boards and the tables
    exports/v272_contained_hall_merge/               the boards and the clips

No GDScript is changed. No earlier profile is changed. No physics, replay,
camera, timing, audio or overlay module is touched.
