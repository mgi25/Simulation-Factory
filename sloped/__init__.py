"""The sloped race: the approved visual course, made physical.

`marble-sloped-course-lab` locked a shape - layout B, ZIG-ZAG RACEWAY, 237
units of channel over a 37-unit drop - and recorded it in
`docs/validation/sloped_course/physics_layout.json`. Nothing in that branch
simulated. This package is the PyBullet pass that brief asked for, and it is
built on `marble3d` rather than beside it: the world, the solver settings, the
mesh chunking, the replay schema and the determinism guarantees are the ones
`marble-physics-core` measured and `marble-v1` shipped.

Read `sloped.scale` first. It is the only place the two coordinate systems in
this branch meet, and everything else in the package is in one of them and
says which.
"""
