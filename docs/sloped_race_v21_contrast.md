# V21 — the readability pass

Status: **materials, grade and light energies over the locked V20 picture.** No
physics, no re-simulation, no course geometry, no camera, no edit, no replay,
no start mechanism, no obstacle or fork logic, no racer skins. Seed 5432 is
untouched and the race outcome is bit-identical, because nothing in this pass
is downstream of anything that decides it.

    docs/validation/sloped_race_v1/v21/contrast_sheet.png   all 11 moments, V20 | V21
    docs/validation/sloped_race_v1/v21/phone.png            the same, at phone size
    docs/validation/sloped_race_v1/v21/pair_<moment>.png    one moment, half resolution

## The problem, measured

Eleven frames, one per cut of the shipped camera track, taken at each cut's own
midpoint so every one of them is a frame of the film rather than a picture near
one. Same replay, same camera track, one build of one scene.

| | V20 | V21 |
|---|---|---|
| pixels at 242+ in **every** channel — flat white | **5.54 %** | **0.87 %** |
| pixels at 250+ in any channel | 9.16 % | 4.09 % |
| pixels above L\* 88 | 11.20 % | 7.08 % |
| pixels above L\* 78 | 17.51 % | 11.52 % |
| 99th percentile of frame lightness | L\* 99.8 | L\* 96.8 |
| mean frame lightness | L\* 37.3 | L\* 34.0 |
| racer vs. its own surround, ΔE | 30.0 | 32.8 |
| racer vs. its own surround, chroma only | 23.6 | 26.9 |

The top line is the finding. **One frame pixel in eighteen was paper white**,
and in the finish shot it was one in seven. That is not a bright picture, it is
a clipped one: where a surface clips it stops shading, so the pearl channel had
no curvature left to read, and the eight racers — 8 to 14 pixels across at
phone size, 40 at the finish — were being asked to compete with a light source
the size of the frame.

The racer separation numbers are measured by projecting each marble's replay
position through the solved camera and comparing a disc of pixels on the ball
against the annulus of course immediately behind it. That is why the finish
shot reports only two racers: the rest are off frame, and an occluded marble
whose projected centre lands behind geometry reports a false near-zero. The
number to read is the direction, not the absolute.

At phone size — the same frames resampled to 270×480, which is roughly what a
1080-wide Short occupies on a handset — ΔE goes 30.6 → 33.4 and chroma 23.9 →
27.2, so the gain survives the resample rather than living in detail nobody
sees.

## What changed

Three files of GDScript, and one new override table inside one of them.

### 1. The pearl family came down between a quarter and half a stop

`lab_palette.V21_RETUNE`. Every moulded white surface — lip, track, shell,
shade, the finale's warm pearl, the light checker tile — loses 0.23 to 0.45
stops of albedo and gains roughness, with the clearcoat lobe narrowed to
match. Value alone would have produced a darker flat surface; roughness is
what puts the shading back. The polished running surfaces keep their metallic,
which is what makes a candy sphere pop off them, and broaden their lobe so the
channel returns a form-revealing sheen instead of one blown flare.

Pearl is still pearl. `tests/test_sloped_contrast.py` holds the bound: nothing
may fall below 70 % of the luminance it shipped with, the white family stays
well clear of a grey card, and every one of them keeps `R > B` and a channel
spread under 0.14 — which is the palette's own "every neutral is tinted, and
pearl runs warm" rule, checked rather than asserted.

### 2. The edge lights got about 40 % quieter

The brightest thing in any frame, and the only one that runs continuously
along every metre of track. Cyan 10.0 → 6.0, violet 10.0 → 6.0, blue 8.5 →
5.3, orange 8.0 → 4.9, gold 7.0 → 4.4. **Only the energies.** The zone story —
cyan off the line, violet into the choice, the two route identities at the
fork, gold from the merge to the flag — is how a viewer four seconds into a
Short knows roughly where in the race they are, and the test asserts that no
edge light changed anything but its energy.

### 3. The glow threshold went above what a lit pearl surface renders at

`glow_hdr_threshold` 1.16 → 1.34, with intensity 1.10 → 0.95 and bloom 0.26 →
0.19. At 1.16 the *track itself* was over threshold, so the running channel was
being bloomed — which is exactly why the white ribbon had no edge. Every
practical and every edge light is still far above 1.34 and keeps its halo.

### 4. The grade stopped amplifying the clip

`adjustment_contrast` 1.06 → 1.00, saturation 1.20 → 1.26. A grade contrast
above one is a gain about mid grey, so it was pushing the top of the range
further into the clip the rest of the pass is trying to recover. The
separation is bought back as saturation instead, which costs pearl nothing —
pearl has almost no chroma to amplify — and pays the racers directly.

### 5. Four light energies, and no light added, moved or recoloured

| light | V20 | V21 | why |
|---|---|---|---|
| `Key` (course) | 3.2 | 2.7 | 3.2 over a 0.89-linear pearl is three and a half times what the curve holds |
| `WorldKey` (terrain) | 2.9 | 2.45 | same fraction as the course key, so the hill keeps its V20 relationship to the track |
| `WorldFill` | 0.95 | 0.68 | the only light that can only ever *reduce* contrast; a third of it was the lavender wash |
| `ValleyBounce` | 1.15 | 0.85 | near-pure diffuse fill, and it lands hardest on the widest pale surfaces |
| `Rim` | 2.3 energy / 1.5 specular | 1.75 / 2.1 | see below |

Ambient sky energy 0.42 → 0.35, which reaches every upward-facing plane and so
was the last of the pearl's clip and most of the terrain's. Fog density 0.0016
→ 0.0019 and aerial perspective 0.72 → 0.80, because half the work distance
was doing was being done by value range and the value range just came down.
SSAO tightens (radius 0.90 → 0.70, intensity 2.1 → 2.7, `light_affect` 0.12 →
0.22) — at 0.12 the lit face of the track, which is most of it, had no
occlusion at all, and `light_affect` is what lets local form survive on a
surface the key is pointed straight at.

### 6. The racers: a response change, not a skin change

The rim light is on no cull mask, so it reaches the racers and the course
alike — and it was reaching them in the wrong proportion. On a pearl drum at
roughness 0.34 nearly all of it arrives as diffuse, which is a second key on
the frame's largest pale surfaces. On a marble at roughness 0.08 under a full
clearcoat nearly all of it arrives as specular, which is the cool edge that
lifts a candy sphere off whatever is behind it. So V21 trades the one for the
other: **less rim light, more of it specular.**

On the marble material itself, `rim` 0.22 → 0.42, `rim_tint` 0.85 → 0.95,
`clearcoat_roughness` 0.02 → 0.05. The eight hues, their saturation and their
body values are exactly as shipped — the test asserts the V21 branch of
`marble()` mentions neither `albedo` nor `MARBLE_COLOURS`, and that no key in
the retune table begins with `marble`. What the wider, more tinted fresnel
buys is a ring of the marble's *own colour* around its silhouette, which is
what lets a ten-pixel ball keep an edge over a light track; the broader
clearcoat stops it answering the key with a single blown white dot that, at
that size, is a third of its area.

Skins are a later pass. This one had to be done first, because a new skin
judged against a clipped background is a skin judged against noise.

## How it is gated

`lab_palette.new("tower", "v21")` is the only thing that turns any of it on,
and `sloped_race_scene.gd` is the only scene that asks for it. Every other
entry point — the visual lab, the track lab, the hero build, and this scene's
own parent, the layout proof — constructs the palette with no contrast pass
and gets the V20 look.

That is checked and not merely intended. Rendering the eleven section frames
with `--contrast=` (empty, which overrides the race scene's default) produces
frames that are **byte-identical to the V20 renders** — eleven of eleven, by
SHA-256. Every earlier lab's committed proof therefore still reproduces from
this branch, which is the same rule the `_v2` and `_hero` key blocks in
`lab_palette.gd` were added under.

## What this pass deliberately did not do

* **The structure stayed.** Nothing was removed. Supports, gantries, rails,
  ribs, beads, piers and catwalks are all present and in place. What changed
  is that `graphite` and `graphite_soft` lost most of their lacquer, so a
  plate the key is pointed at stops returning a hard white streak — those
  streaks were most of what made the support bays read as busy rather than as
  structure — and chrome and gold roughened, so the bead line every half metre
  of track stops being a row of pinpoint mirrors.
* **The environment was left alone.** No mountain, cloud bank, dusk slab,
  distant tower, bush or boulder was moved, rebuilt or repainted. The terrain
  is darker only because two of the lights aimed at it came down.
* **The finish keeps its identity.** Gold is retuned for roughness and
  specular and never repainted; the checker's dark tile is not touched at all,
  because darkening both tiles would preserve the ratio and lose the read.
* **Route identity holds.** Blue is still blue-dominant and orange still
  orange-dominant, each a half step deeper so a pale wash stops competing with
  a saturated racer. The split has to be readable as a *decision* at phone
  size, and the test asserts the dominant channel of each.

## Reproducing

    $env:GODOT_BIN = "...\Godot_v4.7.2-stable_win64_console.exe"

    # the V21 frames
    & $env:GODOT_BIN --path godot res://scenes/SlopedRaceRender.tscn -- `
        --out-dir=<abs>/output/sloped_race_v1/v21/after `
        --replay=<abs>/output/sloped_race_v1/race_5432.json `
        --cameras=<abs>/output/sloped_race_v1/cameras_5432.json `
        --start-contract=<abs>/output/sloped_race_v1/start_contract_5432.json `
        --at=1.058,3.083,4.550,5.642,6.742,7.858,9.725,12.150,14.017,15.283,17.558 `
        --width=1080 --height=1920 --layout=b --detail=hero

    # the V20 control: the same command with --contrast= appended
    # the sheets
    python tools/sloped_contrast_sheet.py --before .../before --after .../after `
        --out docs/validation/sloped_race_v1/v21 --pairs

The eleven output seconds are the midpoints of the eleven cuts of
`cameras_5432.json`; `tools/sloped_contrast_sheet.MOMENTS` is the list and the
name each one goes by. The start contract is rebuilt by
`tools.sloped_start_contract.contract("both")` and is not in the branch,
because `output/` is not.
