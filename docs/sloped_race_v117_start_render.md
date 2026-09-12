# V1.17 — the start the physics runs, and the choice the camera missed

Status: **presentation parity only.** The physics is frozen and byte-identical:
the selected replay for seed 5432 still carries state digest
`aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6`, and nothing
under `sloped/` changed except `cameras.py`, which produces a camera track and
no geometry.

Read [`sloped_race_v115_final_shoulder.md`](sloped_race_v115_final_shoulder.md)
for the production physics this presents.

## The start: the brief's diagnosis was half right, and the half that was wrong matters

The brief gave the defect as *bay pitch 1.1053 against a rendered 0.63, lanes
1.75 times too close, deck 4.11 units low*. Measured, **only the height is
real**:

    layout.BAY_PITCH            = 0.63          the single source of truth
    describe()["bay_pitch"]     = 1.105263      = to_sim(0.63)
    course_modules.BAY_PITCH    = 0.63          read from the same table

`ShuffleFloor.describe()` converts that one field to simulation units while
reporting every other field in layout, so 0.63 and 1.105263 are **the same
number twice** and the render's pitch has never been wrong. Confirmed against
the replay: the eight racers sit at x = -2.210 to +2.207 in the module's own
frame at t = 0, spaced 0.62 to 0.64.

**The height was the whole defect.** `ShuffleFloor.derived_lift` asks for the
elevation its apron, chamber floor, outlet fall and 17-degree chute need, gets
3.929178, and adds it to `layout.NODES["start"]`. `course_machine._modules`
placed the module on the node. So the drawn start stood 3.93 layout units under
the field and the eight racers hung in mid-air for four seconds.

That is also why it was a *whole different machine*: V1.8 replaced the fan pod
with a mixing drum, and V1.9 through V1.16 all shipped the pod.

### What ships

`course_modules.shuffle_start()` builds the housing the physics has: a pan of
eight bays on the apron's own 14-degree ramp, a 2.7-radius acrylic drum with
its inlet open where the pan feeds it, a 2.9 catch cone, an exit chute at the
physics' own grade, and a frame to stand it on.

**None of it is authored.** `tools/sloped_start_contract.py` reads the built
module - origin, yaw, lift, every derived height, and the half-extents of all
thirty kinematic parts - and writes JSON the renderer consumes. So a physics
start that changes moves the render with it.

**And the mechanism is played, not reimplemented.** The eight gate paddles,
four rotor blades and eighteen trapdoor slats are `marble3d` actuators, and the
replay already records a transform for each of them every frame. The scene
draws a box at the size the solver was given and sets its pose from the file,
the way it already does for the marbles and the spinner wheels. There is no
release law, no mixing law and no trapdoor law in the renderer for a later
physics change to leave behind.

### Support, measured on the two files a render is made of

The renderer draws a marble at the replay's marble transform and a slat at the
replay's slat transform, so *"is the field supported"* is answerable without a
renderer. Over the hold - 1.50 s to 5.90 s, after the spawn settles and before
the floor opens - **2112 marble-frames**, gap between each marble's lowest point
and the top of the slat under it:

    max  +0.0011   (+0.002 of a radius)      no marble floats
    min  -0.0108   (-0.022 of a radius)      solver contact slop
    mean -0.0004   median -0.0000

`tests/test_sloped_start_render.py` pins that, the bay alignment, the contract
against the module, and the unit trap that made the pitch look wrong.
`docs/validation/sloped_race_v1/start_v17.png` is the frame.

### Two defects the first build of this had, both found by looking

* **A drawn rotor hub through four racers.** `ShuffleFloor.rest_radius` is zero
  - the field rests anywhere on the disc, the axis included - so a hub is a
  wall the physics has not got. The spindle now starts a marble's height clear
  of the floor and hangs from a gantry.
* **A floor that read as no floor.** The slats were drawn in acrylic and
  vanished against the catch cone below. They are the surface eight racers
  stand on for five of the six seconds before the gun, so they are drawn in the
  polished metal the channel uses.

## The branch choice: the authored `split` node is not the fork

`layout.NODES["split"]` is (6.0, 10.5, 18.0), which is where **blue's lead
begins** - 10.9 layout units downstream of the divider with orange's lead
already gone. Every camera aimed at it framed the aftermath of a choice.

The cut now aims at a `fork` node derived from the built runs: the midpoint of
leg3's own fork sample and the two lead entries. A **fixed** aim, which a pack
aim could not be - the pack is a centroid between marbles, so it is never on
the divider, and it steps across to the other lobe when the leader does.
Extending the old pack shot was measurably worse rather than better: swept
against `frame_report` over three replays, racers in frame across every cut
went 215, 215, 214, 210, 203 at holds of 0.0 to 0.9.

Held 1.6 s, the cut runs 15.35 to 17.67 s with **8 of 8 racers in frame**. On
this replay the first racer takes orange at 16.07 s and the first takes blue at
17.17 s, so both decisions are inside one shot, which is section 9's "one
strong shot rather than several confusing cuts".
`docs/validation/sloped_race_v1/v117/branch_choice_v17.png`.

## Travel per tick, for the selected seed

    seed 5432   max travel per tick inside the machine   0.26186
                = 0.262 of a diameter, budget 0.5
                tick 2212 (9.21667 s), marble 0, 62.85 wu/s
                nearest run leg1[76] - leg1's banked plunge
                touching nothing; airborne between contacts
                clearance 2.373 ahead, 0.583 to the nearest surface

**Category A: legitimate high-speed motion, comfortably inside budget.** The
core's own note describes this exact regime - "a marble on leg1's plunge at 63
to 67 wu/s, 0.288 of a diameter against the 0.5 budget" - and the shipped race
never gets closer to the budget than 0.262 with more than half a diameter of
clearance to anything.

**The 0.746 is not this seed.** It is the maximum over all 600 races, and
0.746 / dt puts it at about 179 wu/s. That is two and a half times anything the
selected race reaches and well into the free-fall regime the `max_travel_falling`
split exists to separate - but the "inside the machine" test is the machine's
**bounding box**, which on a course spanning a gorge contains a great deal of
empty air. So the likeliest reading is category B, a measurement-semantics
question about that box rather than a contact risk. **That is a hypothesis and
it is not resolved here**: it belongs to some seed of the 600 that would have to
be found, and the brief freezes physics. Nothing was changed and no budget was
raised.

## What did not change

The start physics, `ShuffleFloor`, the fork pan, the fork crest, orange's rail,
both routes, the merge, the final shoulder, the PyBullet parameters, 240 Hz and
seed 5432. The merge and finish lenses are as V1.15 left them; their cut
boundaries move only because `split` now holds longer.

## The video

    output/sloped_race_v1/real_race_v17.mp4
    1080x1920, 60 fps, no audio, 1568 frames = 26.13 s, 37.5 MiB

PyBullet remains authoritative at 240 Hz and Godot resimulates nothing.
