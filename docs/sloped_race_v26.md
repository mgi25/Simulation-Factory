# V26: the viewer format and the finished world, in one film

V24 and V25.2 were developed against the same race and never against each
other. V24 asked what the first three seconds should be and answered it in a
20.13 s Short with a hook, a marked racer, a solved edit and a payoff plate,
rendered in the world V22.1 happened to have. V25.2 asked what the race should
be *in* and answered it with a valley that has geometry between the ground and
the sky, rendered through its own proof cameras over V22.1's edit.

V26 is the first film that is both. It is an **integration pass**: it renders
V24's film, frame for frame and instant for instant, in V25.2's world and
V23B's machine colours. Nothing here re-times, re-solves, re-cuts or
re-simulates anything.

    V26  =  V24 format  +  V25.2 world  +  V23B machine  +  meridian racers

**One thing is not a pure combination of the two, and it is in section 14.**
V25.2 put a rock in the line between V24's finish camera and the winner, and
for seven frames of the film's payoff the ring labelled WINNER sits on bare
stone. V26 moves that one rock three units. Everything else in this document is
a measurement of an unchanged thing.

---

## 1. Purpose

To produce the candidate production baseline: the format that is being tested
on YouTube, in the world that was signed off as final, with the machine colour
language that was chosen from three. And to find out - by measuring rather than
by assuming - what combining them breaks.

The specific risk the pass was run to answer is that **every V24 decision was
taken against a world with almost no near geometry.** The hook framing, the
three omissions, the finish camera and the payoff band were all measured on
V22.1's pictures. V25.2 has 174 scattered rocks, 117 trees, 42 boulders, 33
scarps, 26 ridges and 22 spires in it. A composition that worked against an
empty hillside is not thereby proven against a full one.

## 2. Source: V24

Branch `v24-integration`, head `c27f1b9`. Five commits, cherry-picked in
chronological order onto the V25.2 base:

    7c45514   V24 hook lab           sloped/v24_hook.py       b_gate, the framing
    540cac9   V24 pacing lab         sloped/v24_timeline.py   the candidate cuts
    92a4bc4   V24 payoff lab         sloped/v24_payoff.py     the PURPLE WINS plate
    af63d02   visible marble spin    sloped/v24_spin.py       the meridian marker
    c27f1b9   V24 integration        sloped/v24.py            the film

What V24 contributes: no course preview, the `b_gate` opening, PICK A COLOR on
frame zero over live footage, first mechanism motion at 0.117 s, a 20.133 s
timeline, a slope-1 edit map with three omissions, the meridian racer surface,
the PURPLE WINS plate with its 6TH → 1ST line, the winner's ring moved onto the
crossing, V22.1's cue policy and the V24 QC gates.

## 3. Source: V25.2

Branch `v252-final-world-lookdev`, head `9496dd1`, which is this branch's base
and therefore arrives as history rather than as a cherry-pick. It already
carries V23's environment-profile architecture, V23's Aurora direction, the
V23B machine palette, V25's world geometry, V25.1's art pass and V25.2's final
lookdev.

What V25.2 contributes: real 3D world geometry in three depth bands, parallax,
the faceted rock kit, tempered midground shading, terrain material zones, the
vegetation kit, controlled warmth, the finish basin, the obstacle's slate
pocket, the final light rig and the final material treatment.

## 4. Integration strategy

The two lines fork from `e697a12`, V22.1's integration, and neither touched the
other's files. V25.2's line is the base; V24's five commits are cherry-picked
onto it. No merge.

The ownership rule was enforced by the file list rather than by care:

| owner   | owns                                                        |
| ------- | ----------------------------------------------------------- |
| V24     | hook, timeline, edit schedule, overlays, payoff, racers, audio timing |
| V25.2   | environment profile, geometry, rock, vegetation, terrain, lighting, atmosphere, materials |
| V23B    | machine palette and zone language                           |
| physics | itself                                                       |

**The physics freeze has a proof rather than an assurance.**
`output/sloped_race_v1/race_5432.json` is byte-identical on `v24-integration`
and on `v252-final-world-lookdev`:

    race_5432.json            29f9859cde8e152d   both branches
    cameras_v221_5432.json    7471610c0fe0241e   both branches
    preview_v221_5432.json    682280073acb0be2   both branches
    start_contract_5432.json  5d46e7c8a42e055c   both branches

So the replay V26 renders is the replay both lines rendered. The seed is 5432,
the digest is `aafb0d3d…f17de6`, the finish order is 5, 2, 7, 4, 1, 6, 3, 0 and
the winner is marble 5, PURPLE - not because V26 preserved them but because V26
never had a copy of them to diverge from.

## 5. Conflicts, and how they were resolved

Four of the five cherry-picks applied clean, including V24's one modification
to `godot/scripts/sloped_race_scene.gd`. The integration commit conflicted in
exactly the two files both lines had edited, and in both cases the conflict was
**two independent additions to the same table**:

| file                   | ours (V25.2 line) | theirs (V24)  | resolution |
| ---------------------- | ----------------- | ------------- | ---------- |
| `tools/sloped_v22.py`  | `v23` edition     | `v24` edition | both kept  |
| `tools/sloped_short.py`| `v23` edition + paths | `v24` edition + path | both kept |

Neither side was taken wholesale. The import line was merged by hand
(`v23` *and* `v24`), and each edition table now carries every edition it
carried on either branch: `v20, v211, v21, v22, v221, v23, v24` in the Short and
`v22, v221, v23, v24` in the renderer, plus `v26`.

### The one semantic change beyond merging

`tools/sloped_v22.py` gained `borrows_track()`. V26 renders **V24's own solved
camera track file** rather than a copy of it - the arrangement V23 already uses
with V22.1's - and `stage_solve` writes to `race_track_path`, so a V26 solve
would silently overwrite the track V24 ships. V23 relies on a docstring to say
"`--stage solve` is not part of a V23 build"; V26 declares `borrows_track:
"v24"` and `stage_solve` raises. `--stage all` drops the stage instead of
failing on it.

V23 is deliberately **not** given the field. Making it declare one would change
what `--stage all --edition v23` does, and V23 is a shipped edition this pass is
not entitled to alter.

### The one V23 test that had to move, and why it is not a V23 change

`test_no_older_edition_gained_a_v23_flag` skipped `v23` and then asserted that
no other edition carries `--environment=` or `--machine=`. That was the same
set as "every edition older than V23" only for as long as V23 was the newest
edition. V26 is entitled to both dials, so the exemption is now a named list -
`("v23", "v26")` - and the test asserts up front that `v22` and `v221`, the two
editions that actually predate V23, are still in the checked set. The assertion
the test's name makes is unchanged; what changed is that it now expresses it
directly rather than through a proxy that expired.

## 6. The V26 source of truth

`sloped/v26.py`, and nothing else in the repository spells a V26 dimension out.
Both edition tables import `SCENE_FLAGS` from it; a test fails if either starts
writing `aurora_valley_v26` or `meridian` into its own entry.

    ENVIRONMENT = "aurora_valley_v26"      the world   (see section 14)
    BASE_ENVIRONMENT = "aurora_valley_v252"
    MACHINE     = v23.MACHINE              "v23b"
    RACERS      = v24.RACERS               "meridian"
    PREVIEW     = None                     no course preview
    EDIT        = v24.EDIT                 "v24"
    PAYOFF      = v24_payoff.RECOMMENDED   "plate"

The schedule is not restated, it is **imported**: `v26.HOOK is v24.HOOK`,
`v26.START_WINDOWS is v24.START_WINDOWS`, `v26.OMISSIONS is v24.OMISSIONS`,
`v26.build_race_track is v24.build_race_track`. "V26 keeps V24's timing" is an
identity test, not a numerical one.

The four dimensions reach Godot as four flags through four independent options:

    --finish-sign=double  --environment=aurora_valley_v26  --machine=v23b  --racers=meridian

`course_scene` resolves them by four different doors - the profile is an
override table applied over a built material, the machine pass is a constructor
argument to `lab_palette`, the racer surface is a texture in the racer
material's own albedo, the contrast pass is the grade - so none can shadow
another. The V26 profile's world surfaces and `v23b`'s machine surfaces are
disjoint sets, asserted.

## 7. The hook, under the new world

This was the pass's first question and the brief's Part A: `b_gate` was framed
against a world with no near geometry.

**The geometry of frame zero cannot change and did not.** The camera track and
the replay are V24's own files, so the projection is identical by construction:

| frame-zero measure      | V24     | V26     |
| ----------------------- | ------- | ------- |
| racers in frame         | 8 / 8   | 8 / 8   |
| median racer diameter   | 146.24 px | 146.24 px |
| occupancy               | 0.156   | 0.156   |
| racer ink share         | 6.61 %  | 6.61 %  |
| off centre              | 0.0815  | 0.0815  |
| worst disc visible      | 0.839   | 0.839   |
| first mechanism motion  | 0.1167 s | 0.1167 s |
| first camera motion     | 0.1667 s | 0.1667 s |
| first marble motion     | 0.2333 s | 0.2333 s |

**What can change is the picture, and it improves.** Re-scored on the rendered
frames with the hook lab's own instruments:

| rendered measure                     | V24   | V26   |
| ------------------------------------ | ----- | ----- |
| baseline `text_plate` chooses        | 269   | 269   |
| PICK A COLOR worst column, 1080×1920 | 7.92  | 8.82  |
| PICK A COLOR worst column, 270×480   | 7.96  | 8.84  |
| PICK A COLOR mean contrast           | 12.81 | 15.37 |
| racers legible (ΔE and hue)          | 8 / 8 | 8 / 8 |
| weakest racer ΔE, 1080×1920          | 47.1  | 65.5  |
| weakest racer ΔE, 270×480            | 47.0  | 67.6  |

The bar is 3.0:1 for the mark and V26 clears it by 2.9×. The V25.2 world behind
the start is darker than V22.1's (mean luma 113.0 → 95.4 at frame zero), and a
warm-white mark and eight saturated spheres both gain from that. **The
environment did not have to be dressed and the camera did not have to move.**

## 8. The V25.2 world under V24's cameras

The world reads as genuinely three-dimensional, and the clearest evidence is the
merge at output 15.27: in V24 the upper third of that frame is a flat near-black
void and the ground is one smooth mass, and in V26 the same frame is layered
blue rock with faceted cliffs, strata and trees behind the track. The same is
true at the branch and the descent.

The world is also consistently darker and very much cooler. Measured over the
sixteen comparison moments, mean luma and the warm-pixel fraction:

| moment           | V24 luma | V26 luma | V24 warm | V26 warm |
| ---------------- | -------- | -------- | -------- | -------- |
| frame 0          | 114.7    | 97.3     | 4.04 %   | 4.31 %   |
| mixer            | 111.9    | 70.3     | 27.92 %  | 1.09 %   |
| descent          | 99.6     | 69.8     | 30.55 %  | 0.40 %   |
| obstacle         | 113.6    | 93.9     | 19.62 %  | 10.15 %  |
| fork approach    | 104.2    | 51.1     | 46.73 %  | 7.61 %   |
| split            | 91.1     | 44.3     | 49.67 %  | 4.24 %   |
| branch           | 77.2     | 52.0     | 42.54 %  | 4.24 %   |
| merge            | 60.5     | 53.5     | 4.56 %   | 4.07 %   |
| final approach   | 65.2     | 59.0     | 13.61 %  | 13.47 %  |
| winner crossing  | 86.8     | 75.0     | 41.60 %  | 19.01 %  |
| payoff           | 104.5    | 75.9     | 45.12 %  | 16.42 %  |

V24's world is a warm sunset and half its mid-race frames are warm by area.
V26's is a cool valley. That single fact is behind most of what follows,
including the machine result and the payoff result.

Clipping stays negligible throughout - the worst frame in either film is the
merge, at 0.368 % in V24 and 0.478 % in V26, against the 5.5 % that the V21
readability pass was built to remove.

## 9. The V23B machine palette

    start   cyan / cool      mixer  violet       track   silver / pearl
    split   orange / amber   finish gold         supports graphite

The brief's five conflict risks, checked shot by shot:

**Cyan track into cool cliffs** - no. The track's rails are near-white with a
cyan emissive edge and the cliffs are dark, unsaturated blue; the separation is
value, not hue, and it is large.

**Violet mixer into a blue-violet world** - the paddles are the weakest of the
five and they still read. V24's are orange against a warm sky, which is the
louder reading; V26's pale lilac paddles read as *light on dark* against the
valley, and the drum's violet ring is the stronger identity cue. Acceptable, and
the one place where V24's machine is more emphatic than V26's.

**Orange fork competing with warm terrain** - this is the biggest win in the
pass, and it is the reverse of the risk. In V24 the orange fork machine sits on
a warm orange hillside at 46.73 % warm pixels and has to fight for its own
colour. In V26 the terrain at the fork is 7.64 % warm and the orange reads
unmistakably. Part F is satisfied by the world change alone.

**Gold finish competing with a warm finish basin** - no. The finish moment is
41.60 % warm in V24 and 17.55 % in V26; the gold gantry has *less* competition,
not more.

**Graphite supports into dark rocks** - no, and again reversed. In V24 the
supports at the merge stand against a near-black sky and effectively vanish; in
V26 they are dark silhouettes against textured mid-blue rock and read better.

No machine value was weakened and no local environment value was changed for
any of this.

## 10. Meridian racers

Unchanged from V24: the marker is a greyscale texture in the racer material's
own albedo map, carried by the transform the replay already sets. No synthetic
rolling law, no independent marker animation, no second transform. The recorded
quaternions are asserted to be unit and non-identity.

Re-measured against V25.2 backgrounds, marble/background separation improves
(weakest ΔE 47.1 → 65.5 at full size, 47.0 → 67.6 at phone size, 8/8 legible at
both). The markers remain visible through the mixer, the descent, the fork and
the finish; the darker world helps a saturated sphere more than it hurts a
greyscale marker.

## 11. The timeline, and the cut/environment audit

V24's final timeline from `c27f1b9`, unrebuilt. Runtime 20.133333 s over 1208
frames; every segment slope 1; three omissions, all window boundaries:

    spin   replay 2.050 → 4.483    output 1.850
    fall   replay 6.417 → 6.717    output 3.800
    trap   replay 13.583 → 14.033  output 10.683

**The new question this pass had to ask** is whether V25.2's close geometry and
stronger parallax expose a join that was invisible against a sparse world. The
QC's own join check is geometric - it measures visible-face change on the
marbles - and is therefore identical in both films by construction, so it cannot
answer this. `tools/sloped_v26.py --stage joins` measures the **pixels**: the
mean absolute luma step across the cut, against the median step over the six
ordinary frame pairs around it.

| omission | V24 across / typical / ratio | V26 across / typical / ratio |
| -------- | ---------------------------- | ---------------------------- |
| spin     | 4.051 / 4.206 / **0.96**     | 4.754 / 4.792 / **0.99**     |
| fall     | 3.061 / 3.161 / **0.97**     | 3.326 / 3.404 / **0.98**     |
| trap     | 23.746 / 6.027 / **3.94**    | 24.676 / 6.206 / **3.98**    |

**No join is exposed by the new world.** The largest change in any ratio is
0.04. The spin and fall joins are indistinguishable from ordinary motion in both
films. The trap join is a visible step in **both** - about four times its shot's
own typical step - and that is a pre-existing property of V24's cut, not
something V26 introduces; it moved by 1 %.

The reason is worth stating because it is why the brief's concern did not
materialise: an omission here removes replay time while the camera stays on its
own continuous solved path, so the world moves across the join exactly as the
camera does. A close rock cannot jump unless the camera jumps.

## 12. The obstacle

Judged only under V24's pacing, as instructed. The obstacle window is the
longest single shot in the film and V25.2's slate pocket gives it a local
identity it did not have; at V24's speed the shot is legible and does not invite
a second look at the landscape. Warm fraction falls from 19.62 % to 9.99 % and
mean luma from 113.6 to 93.2, which keeps the machine the brightest thing in
frame. No change made, no landmark system opened.

## 13. The fork

The strongest section of V26, and the improvement is the world's rather than the
machine's - see section 9. Both route entrances are open, the rocks do not hide
either, the landscape's own fall supports two directions, and at 270×480 the
orange split machine is the first thing the eye finds in the frame. The marbles
remain readable on both branches.

## 14. The finish, and the one thing V26 changed

This is the pass's real finding.

**The symptom.** V24's WINNER ring opens on the winner's crossing and runs
0.3 s - 18 frames - and the payoff lab moved it there precisely so that it would
sit on a marble somebody can see. Rendered in V25.2's world, the ring spends its
second half over a dark slab with no marble in it.

**The measurement.** The winner is projected through the delivered camera track
at each of the 18 ring frames and the pixel is read back off the **overlay-free**
master, then matched against the eight racer hues. The winner is inside the
frame for all 18 in both films. It is the picture under the ring in:

    V24                            13 of 18
    V26 on aurora_valley_v252       6 of 18
    V26 on aurora_valley_v26       11 of 18

**The cause, found by bisect.** Rendering one frame under four flag
combinations put the machine palette in the clear immediately - with `v23b` and
V22.1's world the pixel is `[206, 78, 241]`, identical to V24's. With V25.2's
world and the shipped machine it is `[15, 26, 38]`. Walking the aurora lineage
narrowed it further: `aurora_valley`, `aurora_valley_v25` and
`aurora_valley_v251` all render the winner purple; only `aurora_valley_v252`
hides it.

Reverting one world section at a time found `world.scarps`, and reverting
`sites` rather than `shape` found the list. Displacing each of the eleven scarp
*sites* off-map in turn - one at a time, with the list length held constant so
that nothing else was re-indexed - found **site 8, at `[31.0, 34.0, 90.0, 1.0]`**.

**The mechanism, which is the part worth keeping.** That scarp is at *identical
coordinates* in V25.1 and V25.2 and is harmless in V25.1. What moved it is that
V25.2 deleted a **different** scarp - the one at `[-48, -72, 60, 0.9]`, sixty
units away - and the scarp builder seeds each site's variation **by its index in
the list**. Removing site 4 re-rolled every site after it, and site 8's new roll
put it in the line between V24's finish camera and the winner's crossing.

So: *deleting a world object in one place silently re-shapes every world object
after it in the list.* V25.2's own proof cameras never looked down that line and
had no way to see it.

**The fix.** `aurora_valley_v26`, a profile that `extends aurora_valley_v252`
and restates exactly one section. `environment.flatten` reports one geometric
leaf between them - `world.scarps.sites` - and inside that list one entry, and
inside that entry one coordinate:

    v252   world.scarps.sites[8] = [31.0, 34.0, 90.0, 1.0]
    v26    world.scarps.sites[8] = [34.0, 34.0, 90.0, 1.0]

Three units, away from the course, so the builder's own clearance can only
increase. The effect saturates: 1 unit gives 9/18, 2 units gives 11/18, and 3, 5
and 9 units all give 11/18. Three is taken for the margin at no cost.

`aurora_valley_v252` is untouched and still selectable, and a test asserts the
V26 profile changes nothing else about the world.

**What the fix does not recover.** V26 reaches 11 of 18 where V24 has 13. The
two frames are at output 17.600 and 17.617, where the marble is in shadow and
reads `[30, 8, 215]` - still plainly a purple sphere to a viewer, but far enough
from `#8E3FD4` that a nearest-hue test assigns it elsewhere. V24 reads
`[85, 25, 213]` at the same instants. This is the darker world, not the scarp,
and it is left alone.

**Two other shots got brighter as a side effect**, which is the same rock coming
out of the same sightline: the final approach rises from mean luma 53.9 to 59.0
and the winner's crossing from 70.3 to 75.0, both measured before and after the
move on otherwise identical builds.

### Finish hierarchy

    1. winner marble   ring and mark, brightest object in frame
    2. finish line     gold gantry, warm, second brightest
    3. PURPLE WINS     plate, top third, over the darkest band available
    4. finish basin    V25.2's warmth, 17.55 % of pixels against V24's 41.60 %
    5. background      dark rock and trees

The warm elements the brief worried about are **less** competitive than V24's,
not more.

## 15. The payoff

V24's plate, unchanged: PURPLE WINS over the winner's own `#8E3FD4`, 6TH → 1ST
beneath it, text at 5.26:1 on its own plate, card up 0.80 s after the crossing
and running 1.8 s to the last frame of the film.

The brief's warning was that the V24 dark band might no longer have the same
contrast because the final world is warmer and brighter. Measured, the opposite:

| tail band                 | V24              | V26              |
| ------------------------- | ---------------- | ---------------- |
| darkest usable rows       | y 296 – 548      | y 0 – 620        |
| worst luma in the band    | 129.9            | 96.5             |
| card ink                  | y 322 – 523      | y 322 – 523      |
| card text contrast        | 5.26 : 1         | 5.26 : 1         |

The band the card must live inside is **wider and darker** in V26, and the card
sits inside it with more room. At 270×480 the purple plate is unmistakable,
WINS and the comeback line are both legible, and no tree, rock or practical
crosses the text.

## 16. Phone review

The 270×480 sheet is `docs/validation/sloped_race_v1/v26/compare_phone.png`.
At phone size the differences that matter are: the fork and split read
substantially better in V26; the merge and branch gain a legible background
where V24 has a void; the payoff plate separates better from its ground; the
mixer paddles are quieter. Racer legibility is 8/8 at 270×480 with a weakest ΔE
of 67.6 against V24's 47.0, and the mark clears its bar at 8.84:1.

## 17. Metrics

`output/sloped_race_v1/v26/metrics.json`, produced by
`tools/sloped_v26.py --stage metrics`. Sections 7, 8, 11 and 14 above are its
tables. Three instrument corrections were needed before any of it could be
believed, and they are recorded in section 21.

## 18. Audio

V24's timing, re-rendered against V26's picture. Not redesigned and not
remixed - the cue policy is V22.1's, which is what V24 uses.

    integrated        -13.90 LUFS       (V24: -13.90)
    loudness range      3.70 LU         (V24:   3.70)
    true peak          -1.51 dBTP       (V24:  -1.51)
    safety limiter     idle             (V24:  idle)

The winner's crossing is the loudest crossing, the loudest moment in the film is
0.12 s after it, and the winner is 7.6 dB over a typical mid-race moment. All
identical to V24, as they must be: the cues are scheduled off the same clock
over the same replay.

## 19. QC

`python tools/sloped_short_qc.py v26` - every gate passes, and **no threshold
was changed**. Against V24's own run of the same QC:

| gate                        | V24              | V26              |
| --------------------------- | ---------------- | ---------------- |
| container                   | 1080×1920, 60/1  | 1080×1920, 60/1  |
| frames / runtime            | 1208 / 20.1333 s | 1208 / 20.1333 s |
| darkest frame luma          | 62.8             | 53.9             |
| mpdecimate keeps            | 1208 / 1208      | 1208 / 1208      |
| opening liveness (px step)  | 3.4855 / 22.58 % | 3.8474 / 24.97 % |
| PICK A COLOR ink rows       | 109              | 111              |
| spin join                   | 1.18×            | 1.18×            |
| fall join                   | 1.26×            | 1.26×            |
| trap join                   | 1.36×            | 1.36×            |
| mixer rotor phase error     | 0.04°            | 0.04°            |
| card text contrast          | 5.26 : 1         | 5.26 : 1         |

## 20. Tests

`tests/test_sloped_v26_integration.py`, 43 tests. They assert the four
dimensions, the one source of truth, the disjointness of the world and machine
surface sets, the four independent options in the scene, the schedule by
*identity* with V24's objects, the borrowed track and its refusal to re-solve,
the physics, the edit map, the one-leaf world delta, the winner under its own
ring, and that V20, V21, V21.1, V22, V22.1, V23 and V24 gained nothing.

Full suite on the delivered branch: **2927 passed, 38 skipped, 1 failed** in
12 m 13 s. The failure is
`test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised`,
which belongs to an unrelated sub-project, asserts on an error message that is
pre-empted by a missing generated replay, and **fails identically on the
untouched base commit `9496dd1`** - verified by running it in a throwaway
worktree at that commit before any V26 work existed.

Two declared dependencies had to be installed for the suite to run at all -
`pymunk` and `pybullet`, both in `requirements.txt` and neither present in this
interpreter. Without them 32 modules fail to import and 50 tests error, none of
them V26's.

Targeted, for the record:

    tests/test_sloped_v26_integration.py                        43 passed
    the four V24 suites + V24 integration                      146 passed, 1 skipped
    V23 env / integration / machine, V25, V25.1, V25.2, env    595 passed, 1 skipped

## 21. Three instrument corrections

Recorded because each produced a confident wrong number first, and two of them
were about this pass's central question.

**`-ss` is not frame-accurate on these files and does not say so.** Measured on
the delivered cut, `-ss 10.6667` and `-ss 10.6833` - one frame apart at 60 fps -
return the same picture, and any seek past the last frame returns the last frame
with exit status zero. That made the trap join measure a luma step of exactly
0.000 and put the payoff and the final frame on the same still. Frames are now
addressed by index through `select=eq(n,N)`, which writes frame N or nothing.

**A replay second is not an output second.** The payoff card was scheduled off
`v24.WINNER_CROSSES` = 20.850, which is a replay second; the film shows that
instant at 17.517 because 3.13 s of replay are omitted before it. The card was
asked for at 21.65 in a 20.13 s film, and `-ss` answered with the last frame.

**`readability.cut_reads` drops racers that have already crossed**, which is
right for a readability bar - "a marble whose viewer already has their answer" -
and exactly inverted for the winner's ring, which opens *on* the crossing. Asked
through it, both films reported the winner in 0 of its own 18 ring frames. The
winner is now projected directly. A fourth, smaller version of the same mistake:
sampling the ring frames off the *finished* film reads the ring's own warm-white
ink rather than the marble under it, and reports the nearest racer as 7 in every
frame of both films. The sample is taken from the overlay-free master.

## 22. Historical reproducibility

**Checked by rendering, not by reading the diff.** Three reference frames per
edition - output 0.000, 6.000 and 17.667 - were rendered on this branch and on
the source commits, from throwaway worktrees, and hashed:

| edition / profile    | rendered on            | sha256 (first 12) of the three frames |
| -------------------- | ---------------------- | ------------------------------------- |
| `v221`               | `9496dd1`              | 5287bc609afe · 58cdaf1c5ff4 · 1669a4b980a6 |
| `v221`               | `c27f1b9`              | 5287bc609afe · 58cdaf1c5ff4 · 1669a4b980a6 |
| `v221`               | **v26-integration**    | 5287bc609afe · 58cdaf1c5ff4 · 1669a4b980a6 |
| `v23`                | `9496dd1`              | cfbb3f5d0e27 · 92097499cc23 · 16c7614c47fd |
| `v23`                | **v26-integration**    | cfbb3f5d0e27 · 92097499cc23 · 16c7614c47fd |
| `v24`                | `c27f1b9`              | 73472be1e712 · b3a3cbf07f51 · ac272644c5bc |
| `v24`                | **v26-integration**    | 73472be1e712 · b3a3cbf07f51 · ac272644c5bc |

and the two V25 profiles, at output 6.000 and 14.000 over V22.1's track:

| profile              | `9496dd1`                    | **v26-integration**          |
| -------------------- | ---------------------------- | ---------------------------- |
| `aurora_valley_v251` | ddfb7101f455 · bdf747629b45  | ddfb7101f455 · bdf747629b45  |
| `aurora_valley_v252` | e06a2d38c930 · 4ee33e7a9eee  | e06a2d38c930 · 4ee33e7a9eee  |

Every historical edition and profile is **byte-identical**. V22.1 also renders
identically on both source commits, which is a second confirmation that the two
lines never diverged on anything the renderer can see.

Nothing V26 adds is visible to an edition that shipped before it. No older
edition gained a V26 flag, a `mark`, a `payoff` or a V25 world;
`DEFAULT_EDITION` is still `v21` in the Short and `v22` in the renderer; the
environment registry's default is still `alpine_neon`; the racer default is
still `solid`; `aurora_valley_v252` is byte-identical and still selectable, as
are `aurora_valley`, `aurora_valley_v25` and `aurora_valley_v251`. V23's scene
flags are still three and still carry no `--racers`. V24's scene flags are still
`--finish-sign=double --racers=meridian` and its edition still writes
`real_race_v24.mp4`.

## 23. Remaining weaknesses

1. **Two ring frames.** V26 delivers 11 of 18 against V24's 13. Both losses are
   shading, not occlusion - the marble is plainly purple to a viewer and only
   ambiguous to a nearest-hue test.
2. **The trap join is a visible step, in both films.** ~4× its shot's own
   typical step on the pixels, where the QC's geometric check reports 1.36×. V26
   did not cause it and did not fix it; it is worth a look in whatever comes
   next.
3. **The mixer paddles are quieter than V24's orange ones.** The v23b violet
   reads, but it is the one place the machine's identity is softer than the film
   it replaces.
4. **The scarp builder's index-seeded variation is a trap.** Adding or removing
   any world site re-rolls every site after it. Nothing here fixes that; it is
   recorded so the next world pass knows.
5. **The fork and split frames are dark** - mean luma 51 and 44 against V24's
   104 and 91. The machine reads better than V24's, so this is a note rather
   than a defect, but it is the largest single change in the film's exposure.

## 24. Files

    output/sloped_race_v1/real_race_v26_master.mp4     silent integrated master
    output/sloped_race_v1/real_race_v26_visual.mp4     picture, no audio
    output/sloped_race_v1/real_race_v26.mp4            the Short
    output/sloped_race_v1/v26/opening_v24_v26.mp4      first 5 s, side by side
    output/sloped_race_v1/v26/compare_v24_v26.mp4      the whole film, side by side
    output/sloped_race_v1/v26/metrics.json             every number above
    docs/validation/sloped_race_v1/v26/compare.png     16 moments, 1080x1920
    docs/validation/sloped_race_v1/v26/compare_phone.png   16 moments, 270x480

All of it is copied to `exports/v26_integration/`, with the ring strip.

## 25. Should V26 become the production baseline?

**Yes, subject to watching the file.**

Every measured axis is equal to V24 or better: frame-zero geometry identical by
construction, mark contrast up 11 %, weakest racer separation up 39 %, no join
exposed, LUFS and true peak identical, QC passing on unchanged thresholds, and
the fork, merge and payoff materially clearer. The one regression the
integration produced was found, diagnosed to a single coordinate, and fixed with
a three-unit move that leaves the rest of V25.2 untouched.

The thing a measurement cannot settle is whether the cooler, darker, much less
warm world is the one the channel wants - it is a different film to look at,
not just a better-built one. That is the judgement the MP4 is for.
