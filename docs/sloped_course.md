# The sloped race course

A long premium downhill marble course on a mountain flank, replacing the
vertical tower composition locked on `marble-final-visual`. That build is kept
as an asset library - `v2_track.gd`, `lab_palette.gd`, `lab_forms.gd`,
`toy_geometry.gd` and `hero_world.smooth_mass` are all reused here unchanged -
and its layout is not.

## Phase 1: the layout study

Three structurally different courses, drawn from the same blockout builder with
the same materials and the same camera rig, so the comparison is of shape only.

| | length | drop | span x / z | start to finish |
|---|---|---|---|---|
| A cliff descent | 145.9 | 31.3 | 31.0 / 70.3 | 82.8 |
| B zig-zag raceway | 165.7 | 31.0 | 32.1 / 60.6 | 73.4 |
| C open mountain run | 143.5 | 32.0 | 34.0 / 82.4 | 90.9 |

`docs/validation/sloped_course/layout_comparison.png`

**B is selected.** It is the longest by twenty units, its four legs are the only
ones that read as *straights* rather than as one continuous snake, and its split
is the only one whose two routes can be told apart at phone size. A and C each
lose the top third of the frame to a thin ribbon; B fills the height with four
terraces, which is also four separate camera positions.

C's split is the widest and best of the three and its idea - branches thrown
right across the terrain and pulled back - is carried into B's development.

## What the study fixed on the way

Two artefacts cost a pass each and are worth not rediscovering.

**The ground has to be on the world's light layer.** The terrain was built in
`course_machine` and never assigned to layer 2, so the warm three-quarter
product key lit it at full energy and every face turned toward that key came
back tan. Read as a material fault it is unfixable; it is a light-mask fault.

**Material bands must be read off the macro surface.** Thresholding a
four-octave heightfield at a fixed height gives a fifteen-unit fringe of
interleaved patches wherever the surface crosses the threshold - camouflage,
not geology. `course_terrain.height(x, z, cfg, false)` returns the same surface
with the noise off, and every band is read from that.

## The bench

`course_terrain` cuts the ground down to a fixed depth below the racing line
wherever the hill would otherwise stand higher than it. That is what a real
installation does, and it means every support has a positive length by
construction rather than by hand-tuned coordinates.
