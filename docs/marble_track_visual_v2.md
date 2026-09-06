# Marble machine — Track + Environment Visual Direction V2 / V2.1

The art that should replace the placeholder Start / Bowl / S-curve visuals in
`marble-v1`. No physics, no replay, no race logic: this branch owns the design
and hands `marble-v1` a table of anchors to adapt to.

Renders: [`docs/validation/track_visual_v2/`](validation/track_visual_v2/) —
`*_v2.png` is the V2 direction lock, `*_v21.png` the current refinement.
Reference breakdown: [`docs/track_visual_lab/VISUAL_BREAKDOWN.md`](track_visual_lab/VISUAL_BREAKDOWN.md).

## V2.1 refinement pass

Two problems with V2, both course rather than style, fixed without touching the
approved visual language.

**Start fairness.** Eight bays on a straight line feeding one chute meant the
bay a racer started in decided where it sat in the stream, and on a chute that
curves the inside lane is simply shorter — a positional advantage that survived
the whole first transition. The fix is a **shuffle deck**: a tilted pan between
the gate and the chute carrying **four staggered rows of chrome deflector
pins**, five and six per row at half a pitch of offset, so every gap in one row
sits behind a pin in the next.

The arithmetic is the design. Pitch 0.90, pin radius 0.115, so every gap —
including the two against the walls — is **0.67 clear against a 0.57 racer**;
the deck's half width of 2.95 falls straight out of needing the edge gaps to
clear as well, which is why the deck is wider than the pod it hangs under.

A deflector field is the answer because it is the *provable* one: no path
through it is shorter than another by construction, and the outcome does not
depend on tuning a curve. It is also the right answer visually — the brief asks
for the advantage to be broken by the first obstacle, and an obstacle you can
see is worth more than a geometric trick you cannot.

The last 0.92 of the deck converges through two vanes to a **3.44 mouth**, which
is what the chute's flared entry actually accepts; the full-width pin field
would otherwise have thrown the outer lanes past it. The taper sits after every
pin row, so it costs nothing in fairness — by the time a racer reaches it, its
lateral position no longer has anything to do with the bay it left. The bowl
then scrambles the order a second time before the hero descent.

**Track width.** The V2 channel was 1.24 clear — two marbles and change, and it
read as undersized beside a bowl twelve marbles across. `HERO_CLEAR_WIDTH` is
now **1.90**: three racers of 0.57 abreast plus working clearance. The whole
profile is authored at unit scale and multiplied by `PROFILE_SCALE`, which is
derived from that one number, so the shell, floor, keel, guards, beads, light
lines and joint straps grew together and the section's proportions are
untouched. Joint spacing went 1.35 to 1.80 to keep the same rhythm on a bigger
part.

Everything the wider channel touched moved with it: the bowl grew to rim 4.15
and dish 3.48 to stay the widest module, the S's swings pulled in to ±2.65 so
the track stays inside the bowl's silhouette, the equipment decks stepped back
to z −3.25, the saddles dropped to clear the deeper keel, and the plinth grew so
the base still reads as a foundation rather than a lid.

## Selected direction

A **premium futuristic marble playset on a cliff ledge at dusk.** Three modules
on one dark architectural core, with a single continuous signature channel
threading from the start line to the bottom of the frame.

The proportion is the decision that mattered most. The first assembled build
was 17 units tall and 9.5 wide and read as a chunky stack of discs; the target
concept is roughly 1 : 3.5. Shrinking the bowl, narrowing the start pod, scaling
the track profile and lengthening the descent brought it to **22.4 tall by about
8.6 wide**, and that single change did more for the "same class as the
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

V2.1 adds the **shuffle deck** below the gate: a graphite-floored pan in a pearl
surround, forty chrome capsule pins, converging vanes and a gold exit lip. The
pins are capsules with the fillet set to their whole radius — anything less
rounded reads as a canister rather than as a deflector, and a cap on top, tried
at two sizes, reads as the rim of one.

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

**Racer scale (V2.1):** the dish is 6.96 across and a racer is 0.57 — about
twelve end to end. Reached by shrinking the bowl, not by inflating the marbles.

**Action clearance:** a cylinder of radius 3.63 and height 2.98 over the whole
running surface. Cradle arms sit on rear bearings only (138°, 200°, 262°); the
one thing that crosses the sightline is the guard, and it is transparent.

## TRACK V2 — the signature channel

`godot/assets/marble_machine/v2/v2_track.gd`

A six-feature cross-section swept with **real banking** — the capability the
previous toolkit could not express, and the reason a new `banked_sweep` exists.
Across the channel: a full-round pearl shell, a rolled lip with a chrome bead, a
recessed emissive line sunk into each shoulder, a darker silver running insert,
and a graphite keel hung below with transverse strap-and-gold-block joints every
1.80 units.

The section is per-sample: `width_curve` flares the mouth, pinches the fast
middle and opens again at the exit. The feed chute uses an entry flare so the
channel itself opens to catch the shuffle deck's mouth and closes to the hero
section within two units — **the start-to-bowl transition is the track, not a
separate funnel.** An earlier build had a moulded funnel there and it read as a
white skirt from every hero angle.

Bank is derived from smoothed horizontal curvature, clamped to 20° on the feed
and 27° on the S, and eased to zero at both ends so a banked run meets a level
module square.

**V2.1 width:** clear span **1.90** (three racers abreast), overall section 2.72
across, driven by the single `HERO_CLEAR_WIDTH` constant.

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

| | value (V2.1) |
| --- | --- |
| visual marble diameter | 0.57 |
| start origin / yaw | (0, 19.80, 0.55), 0.16 rad |
| start bays / pitch / floor | 8 / 0.63 / local y −0.02 |
| shuffle deck entry | (0.00, 19.64, 1.87) |
| shuffle deck pins | 4 rows, pitch 0.90, r 0.115, h 0.30 — **0.67 clear gap** |
| shuffle deck half width / mouth | 2.95 / 1.72 (3.44 across) |
| deck exit → feed entry | (0.62, 18.42, 3.55) |
| feed exit → bowl entry | (−2.30, 13.85, 0.25) |
| bowl centre / rim / dish / drain | (0, 12.60, 0) / r 4.15 / r 3.48 / r 0.70, depth 1.16 |
| bowl exit → S entry | (0.00, 11.44, 0.10) |
| S exit | (1.90, 2.10, 1.20) |
| **hero channel clear width** | **1.90** |
| marble contact offset below section origin | −0.128 |
| pylons / plinth / top | x ±3.30, z −3.70 / y 0.10 / y 21.40 |

Pin positions are not listed here: `Start.pin_positions()` generates them from
the four numbers above and `modules.json` carries the resulting list, so a
physics pass rebuilds the field rather than transcribing it.

## Camera

Hero: **elevation 22°, azimuth 34°, FOV 34°**, aim y 11.3, vertical extent 25.0
(distance is derived from extent and FOV, never typed in). Chosen from the
sweeps in `camera_elevation.png` and `camera_azimuth.png`: below 20° the bowl
goes edge-on and the field stops reading; above 24° the tower flattens and the
plinth takes over the frame. At azimuth 18° the machine reads flat and at 66°
the sign crops.

## Performance

~203k triangles, 654 mesh instances, **≈420 ms/frame at 1080×1920** on an
RTX 3050 Laptop (offline render with MSAA, SSAO, SSR and glow all on). The
environment is a small fraction of that; the ribs, bolt rings and swept channels
are most of it. V2.1 added ~8k triangles — the pin field is forty capsules and
costs almost nothing.

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
- The shuffle deck's floor is a plane: `Start.deck_floor_y(z)` gives its height
  at any pod-local z, and the pins are upright capsules of radius 0.115 and
  height 0.30 standing on it. Colliders are one tilted box plus forty capsules
  plus two vane boxes; nothing about it needs special handling.
- Fairness is geometric, not tuned. If a physics pass changes marble diameter,
  the one number to re-check is the pin gap: `PIN_PITCH - 2 * PIN_RADIUS` must
  stay comfortably above it, or racers will jam instead of scattering.
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
