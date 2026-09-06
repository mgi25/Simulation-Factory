# FINAL HERO MACHINE — visual direction lock

The complete seven-stage marble machine, in one vertical composition, in a dusk
gorge. Branched from `marble-track-visual-lab` at `df43ac8`, which held three
modules built properly; this adds the other four and rebuilds the composition
around all seven.

**No physics.** Nothing here simulates, and nothing here is a fairness claim.
`docs/validation/final_hero_machine/physics_anchors.json` records
`"fairness": "UNVERIFIED - no simulation has been run against this art"`.

## What it is

| # | Stage | Weight | Built from |
|---|-------|--------|------------|
| 1 | START PLATFORM | small landmark | `v2/v2_start.gd`, unchanged: 8 bays, sign, gate, housed mixer |
| 2 | MIXING BOWL | hero | `hero/hero_bowl.gd` — flared glass bell, grooved dish, ribbed belly |
| 3 | S-CURVE BRIDGE | connector | `v2/v2_track.gd` over 7 units, three swings |
| 4 | COLLECTOR | medium landmark | `hero/hero_collector.gd` — pan, five-blade rotor, one gate |
| 5 | SPLIT CHOICE | hero | `hero/hero_split.gd` — blue route, orange route, hazard deck |
| 6 | FINAL COMPRESSION | small connector | `hero/hero_compression.gd` — junction, four closing collars |
| 7 | FINISH ARENA | hero | `hero/hero_finish.gd` — checkered pad, bollards, FINISH gantry |

Structure is `hero/hero_spine.gd`: a segmented dark core threaded through every
gap between two modules, three service rings, two slim outrigger towers at
z = −8.8, three open X yokes, four cantilever brackets. No back wall.

Environment is `hero/hero_world.gd`: four rock layers (near / mid / far / haze)
at separated values, smooth-shaded with three octaves of noise plus strata,
scrub along every crest, distant lit architecture, a warm dusk band and a
valley below.

Every dimension is in `hero/hero_layout.gd` and nothing else invents a
coordinate.

## Render

```
export GODOT_BIN=".../Godot_v4.7.2-stable_win64_console.exe"
python tools/hero_lab.py shots     # hero + phone at 1080x1920, modules at 1200²
python tools/hero_lab.py sheets    # target comparison, phone, module sheet
python tools/hero_lab.py sweeps    # elevation / azimuth / lens
python tools/hero_lab.py motion    # 6 s at 1080x1920 -> output/
python tools/hero_lab.py preview   # fast 540x960, for iterating
```

## Camera

FOV 32°, elevation 18°, azimuth 22°, aim y = 15.75, extent 36.4 — chosen off
the sweeps in `camera_elevation.png` / `camera_azimuth.png` / `camera_lens.png`.
At 21° the dishes open up and the split's left branch disappears behind the
core; at 13° the tower flattens and the bowl's interior closes.

## Five things that cost a pass each

**A cone is not a gorge wall.** The rock builder tapered to 0.22 of its base
radius at the crest, so at two hundred units — with the frame's top edge five
degrees *below* the camera's horizon — only the foot of each mass was in shot
and the gorge read as a scatter of small hills. Cliffs now taper 0.30.

**Distant terrain has to be taller, not just further.** Give every layer the
same crest height and each one behind sits lower in the frame than the one in
front: the background collapses into a staircase falling away from the viewer.
The layers are placed by crest *angle*, and their heights rise with distance.

**One sun cannot light both.** A three-quarter front key is what makes a
moulded pearl shell show its curvature, and it is also what flattens a cliff
into paper, because a large smooth mass lit from the direction it faces has no
gradient across it. There are two directionals with complementary cull masks —
a product key on layer 1, a raking key on layer 2 — and the environment stopped
looking like card the moment they were separated.

**The core is what makes a tower.** The concept's modules are threaded onto a
continuous dark trunk and every gap between two of them is filled by it. Ours
had modules floating with thin towers off to one side, and no amount of
material work closed that gap.

**Connectors must end outside what they feed.** The first assembled build put
the S-curve's last swing on the collector's rim and its first under the bowl's
belly, and the result was one continuous white spiral in which neither disc
could be found.

## Reproducibility

`lab_palette.gd` is extended **purely additively**, as on every branch in this
line. Seven shared keys the hero build wanted at a different setting live as
`*_hero` variants rather than as edits, and `v2_track.gd`'s thicker edge light
is an `edge_stock` option defaulting to the V2.2 value. Checked: rendering
`scenes/TrackLabRender.tscn` from this branch reproduces
`docs/validation/track_visual_v2/machine_v22.png` with **zero** differing
pixels.

## Honest gaps against the concept

1. The concept's split is a wider, more symmetric hourglass; ours converges
   lower and its left branch is partly read against the core rather than
   against background.
2. The environment is colder and simpler — the concept has warm vegetation and
   far more cliff detail. Ours is a dark blue gorge with sparse warm lights.
3. The concept's S-curve is a broader, flatter ribbon with more air around it;
   ours wraps closer to the trunk.

## Cost

~533,000 triangles, 1,466 mesh instances, about 0.5 s per 1080×1920 frame on an
RTX 3050 Laptop. 0.61% of the hero frame is fully blown, all of it lit strips
and hardware rather than pearl surfaces.
