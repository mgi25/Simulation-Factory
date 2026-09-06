# Marble machine — Track + Environment Visual Direction V2

The art that should replace the placeholder Start / Bowl / S-curve visuals in
`marble-v1`. No physics, no replay, no race logic: this branch owns the design
and hands `marble-v1` a table of anchors to adapt to.

Renders: [`docs/validation/track_visual_v2/`](validation/track_visual_v2/).
Reference breakdown: [`docs/track_visual_lab/VISUAL_BREAKDOWN.md`](track_visual_lab/VISUAL_BREAKDOWN.md).

## Selected direction

A **premium futuristic marble playset on a cliff ledge at dusk.** Three modules
on one dark architectural core, with a single continuous signature channel
threading from the start line to the bottom of the frame.

The proportion is the decision that mattered most. The first assembled build
was 17 units tall and 9.5 wide and read as a chunky stack of discs; the target
concept is roughly 1 : 3.5. Shrinking the bowl, narrowing the start pod, scaling
the track profile to 0.84 and lengthening the descent brought it to **22.4 tall
by about 8 wide**, and that single change did more for the "same class as the
reference" test than any material or lighting work.

## START V2 — a moulded launch pod

`godot/assets/marble_machine/v2/v2_start.gd`

One filleted pearl body with heavier end blocks, a graphite belt at the parting
line and a shaded skirt below it; a recessed silver tray cut into the top with
nine dividers making **eight bays, all eight racers visible side by side**; one
acrylic gate bar on gold pivots with an orange paddle per bay; and a lit
**START** sign — real 3D text, not a bright rectangle — in a graphite frame
carried on the pod's own back wall rather than on stilts. Dark chassis under it
with orange drums, gold collars and an equipment rack.

It is deliberately wider relative to the bowl than the reference's start is. A
bay has to be wider than a marble, and "all eight racers readable at the line"
is a stated requirement while "matches the reference's width ratio" is not.

## BOWL V2 — a transparent toy component

`godot/assets/marble_machine/v2/v2_bowl.gd`

Seven concentric parts: an aqua acrylic guard built with **real wall thickness**
(`shell_lathe` walks the profile out and back, so the rim has an edge instead of
ending in a zero-width line), a pearl coping capping it, a heavy machined rim
with a chrome bead and gold inlay and a 36-bolt ring, a silver running dish, a
violet ring light under the dish's outer edge, a visible gold-collared drain
throat you can see down, and a three-arm graphite cradle with gold collars and
orange jacks.

**Racer scale:** the dish is 6.44 across and a racer is 0.57 — about eleven end
to end. Reached by shrinking the bowl, not by inflating the marbles.

**Action clearance:** a cylinder of radius 3.37 and height 2.98 over the whole
running surface. Cradle arms sit on rear bearings only (138°, 200°, 262°); the
one thing that crosses the sightline is the guard, and it is transparent.

## TRACK V2 — the signature channel

`godot/assets/marble_machine/v2/v2_track.gd`

A six-feature cross-section swept with **real banking** — the capability the
previous toolkit could not express, and the reason a new `banked_sweep` exists.
Across the channel: a full-round pearl shell, a rolled lip with a chrome bead, a
recessed emissive line sunk into each shoulder, a darker silver running insert,
and a graphite keel hung below with transverse strap-and-gold-block joints every
1.35 units.

The section is per-sample: `width_curve` flares the mouth, pinches the fast
middle and opens again at the exit. The feed chute uses a large entry flare so
the channel itself opens to the width of the start tray and closes to single
file within two units — **the start-to-bowl transition is the track, not a
separate funnel.** An earlier build had a moulded funnel there and it read as a
white skirt from every hero angle.

Bank is derived from smoothed horizontal curvature, clamped to 20° on the feed
and 27° on the S, and eased to zero at both ends so a banked run meets a level
module square.

## Support system V2

`godot/assets/marble_machine/v2/v2_spine.gd` — five parts, not a scaffold:
**pylon** (a chunky moulded column with panel breaks and a lit channel),
**yoke**, **cantilever**, **saddle**, **plinth**, plus a **back wall** (a
louvred graphite slab the whole machine is built against) and **decks** (small
equipment platforms filling the vertical gaps).

Pylons sit at x = ±3.30, z = −3.70 — outboard of the bowl's rim radius and
behind its centre, so no column crosses a running surface from any front camera.

## Environment V2

`godot/assets/marble_machine/v2/v2_world.gd` — a cliff gorge at dusk, built as a
ring of masses rather than a backdrop, in three depth layers separated by value
as well as by haze: near crests at ~90 units, a far range at ~210, ridge lines
at ~450, plus spires along every crest for a broken silhouette, lit structures
standing on the near crests, warm valley lamps, and a horizon band behind.

Two pieces of arithmetic drove the whole layout and are worth keeping:

1. **The frame is a narrow wedge.** A 34° vertical field on a 9:16 frame is only
   about 20° wide. Scenery has to sit near the view bearing, not merely behind.
2. **The top of the frame is not sky.** The hero camera looks down 22°, so the
   frame's upper edge is 5° *below* the camera's horizon — at 300 units that is
   y ≈ 0. An early horizon band was placed at y = +26 and was simply above the
   shot.

The near crests are spaced to leave a ~15° gap on the view bearing, so the far
layers and the haze read *through* the machine's own gaps. Packed shoulder to
shoulder they made one continuous wall and the gorge became a cave.

## Module anchors

Written by the scene itself to
[`docs/validation/track_visual_v2/modules.json`](validation/track_visual_v2/modules.json),
derived from the same constants the geometry is built from.

| | value |
| --- | --- |
| visual marble diameter | 0.57 |
| start origin / yaw | (0, 19.80, 0.55), 0.16 rad |
| start bays / pitch / floor | 8 / 0.63 / local y −0.02 |
| start exit → feed entry | (0.15, 19.20, 1.80) |
| feed exit → bowl entry | (−2.00, 13.55, 0.00) |
| bowl centre / rim / dish / drain | (0, 12.60, 0) / r 3.86 / r 3.22 / r 0.70, depth 1.16 |
| bowl exit → S entry | (0.00, 11.44, 0.10) |
| S exit | (2.05, 2.10, 1.30) |
| channel clear width | 1.243 |
| marble contact offset below section origin | −0.084 |
| pylons / plinth / top | x ±3.30, z −3.70 / y 0.10 / y 21.40 |

## Camera

Hero: **elevation 22°, azimuth 34°, FOV 34°**, aim y 11.3, vertical extent 25.0
(distance is derived from extent and FOV, never typed in). Chosen from the
sweeps in `camera_elevation.png` and `camera_azimuth.png`: below 20° the bowl
goes edge-on and the field stops reading; above 24° the tower flattens and the
plinth takes over the frame. At azimuth 18° the machine reads flat and at 66°
the sign crops.

## Performance

~195k triangles, 634 mesh instances, **≈420 ms/frame at 1080×1920** on an
RTX 3050 Laptop (offline render with MSAA, SSAO, SSR and glow all on). The
environment is a small fraction of that; the ribs, bolt rings and swept
channels are most of it.

## Integration considerations for marble-v1

- The art was designed first and the colliders should follow it. Every anchor
  above is in the same world units the scene is built in.
- The two chutes are Catmull-Rom splines through the control lists in
  `v2_machine.gd`; a physics pass wants the *sampled* path plus the bank array,
  both of which the module nodes carry as metadata (`path`, `banks`, `widths`).
- `Track.running_point(path, banks, t, radius)` already returns where a marble
  of a given radius rests on the banked floor. That is the mapping a replay
  needs, and it is the only thing that knows about the roll.
- The bowl's drain is at (0, 11.44, 0) with clear radius 0.70; the S's first
  sample is the same point.
- Nothing in this branch imports from `race` or `engine`, and the scene is
  unreachable from `ReplayViewer.tscn` or `OfflineRender.tscn`.

## Biggest remaining visual gap

1. **The environment is supporting, not cinematic.** The gorge reads as haze and
   silhouette, which is enough to stop the machine floating, but its rock is
   coarse faceted geometry and would not survive being looked at directly. The
   reference's background has vegetation, lit roads and warm structures.
2. **Warmth is confined to the base.** Gold hardware is everywhere but warm
   *light* only exists at the plinth, so the frame runs cool top to bottom where
   the reference runs cool-to-gold down its height. A finish zone would fix this
   naturally and is deliberately out of scope here.
3. **Only three of seven stages.** The slice is proportioned to read as part of
   a taller tower, but the reference's density comes partly from having seven
   modules with no dead vertical space between them.
