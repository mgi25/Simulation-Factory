extends RefCounted

## Rounded-form mesh primitives for the premium-toy prototype.
##
## A separate file from the scene that uses it, because this is the part of
## the toy direction that is engineering rather than taste. The brief's
## mandatory rule is that every major module has a bevel, a fillet or a curve
## on it - and Godot ships a box, a sphere, a cylinder and a torus, none of
## which has a rounded edge. Everything the scene builds that is not a sphere
## comes out of the four builders below.
##
## ## Why rounding is worth a file
##
## A hard edge between two flat faces produces exactly one highlight: a line,
## one pixel wide, where the surface normal happens to bisect the light and
## the lens. A filleted edge produces a *band* of highlight whose width is the
## fillet's own radius, and that band is the single strongest cue that an
## object was moulded rather than assembled from planes. It is the reason a
## toy photographs as a toy. It is also why the V1.1 machine reads as
## fabricated steel: every edge in it is a corner between two quads.
##
## ## Winding
##
## Godot's front faces are wound so that `(b - a) x (c - a)` points *away*
## from the surface normal, which is the convention `neon_scene.gd` follows
## by hand. Doing that by hand across quarter-cylinders and spherical octants
## in eight sign combinations is a bug farm, so every quad here goes through
## `quad_auto`, which measures the cross product against the normal it was
## given and reverses the corner order when they disagree.
##
## That costs one cross product per quad, once, at build time. It buys back
## every inside-out surface, and the meshes are built once per render.
##
## ## Determinism
##
## Nothing here reads a clock, randomises, or accumulates. Every builder is a
## pure function of its arguments, so two renders of one replay produce
## byte-identical meshes - the property the whole offline pipeline rests on.

const TAU_ := TAU


# --- quads ----------------------------------------------------------------

static func quad_auto(surface: SurfaceTool, a: Vector3, b: Vector3, c: Vector3,
		d: Vector3, normal: Vector3) -> void:
	## One flat quad, wound to face `normal` whichever order it arrived in.
	var corners := [a, b, c, d]
	if (b - a).cross(c - a).dot(normal) > 0.0:
		corners = [a, d, c, b]
	for index in [0, 1, 2, 0, 2, 3]:
		surface.set_normal(normal)
		surface.add_vertex(corners[index])


static func quad_smooth_auto(surface: SurfaceTool, points: Array,
		normals: Array) -> void:
	## The same, with a normal per corner, for a curved surface.
	##
	## Orientation is decided against the *average* of the four normals: on a
	## fillet the corner normals differ by at most the fillet's own angular
	## step, so their mean is a faithful stand-in for the face and no quad on
	## a curved surface is ever near the degenerate case.
	var mean: Vector3 = (normals[0] + normals[1] + normals[2] + normals[3]) * 0.25
	if mean.length_squared() < 1.0e-12:
		mean = (points[1] - points[0]).cross(points[2] - points[0])
	var order := [0, 1, 2, 3]
	if (points[1] - points[0]).cross(points[2] - points[0]).dot(mean) > 0.0:
		order = [0, 3, 2, 1]
	for index in [0, 1, 2, 0, 2, 3]:
		var at: int = order[index]
		surface.set_normal(normals[at])
		surface.add_vertex(points[at])


# --- the rounded box ------------------------------------------------------

# The three axes, and for each the two others in right-handed cyclic order.
# Used to build the six faces and twelve edges without writing each out.
const AXES := [Vector3.RIGHT, Vector3.UP, Vector3.BACK]
const CYCLE := [[1, 2], [2, 0], [0, 1]]


static func rounded_box(size: Vector3, radius: float, segments := 4) -> ArrayMesh:
	## A box with every edge filleted and every corner spherical.
	##
	## Built as three exact parts rather than as a deformed sphere: six flat
	## faces inset by the radius, twelve quarter-cylinders along the edges,
	## and eight spherical octants at the corners. Exact matters because the
	## flat faces are where a moulded surface shows its shading gradient, and
	## a sphere pushed into a box shape has curvature everywhere.
	##
	## `segments` is the number of quads across one ninety-degree fillet.
	## Four is enough at the scale this machine is framed at; the bowl's
	## visible rounds use more.
	var half := size * 0.5
	var r: float = clampf(radius, 0.0, minf(half.x, minf(half.y, half.z)))
	var core := Vector3(
		maxf(half.x - r, 0.0), maxf(half.y - r, 0.0), maxf(half.z - r, 0.0))

	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)

	_box_faces(surface, half, core)
	if r > 1.0e-5:
		_box_edges(surface, core, r, segments)
		_box_corners(surface, core, r, segments)

	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh


static func _box_faces(surface: SurfaceTool, half: Vector3,
		core: Vector3) -> void:
	for axis in 3:
		var normal_axis: Vector3 = AXES[axis]
		var u: Vector3 = AXES[CYCLE[axis][0]]
		var v: Vector3 = AXES[CYCLE[axis][1]]
		var cu: float = core[CYCLE[axis][0]]
		var cv: float = core[CYCLE[axis][1]]
		if cu <= 1.0e-6 or cv <= 1.0e-6:
			continue
		for sign_index in 2:
			var s := 1.0 if sign_index == 0 else -1.0
			var base: Vector3 = normal_axis * (half[axis] * s)
			quad_auto(surface,
				base - u * cu - v * cv,
				base + u * cu - v * cv,
				base + u * cu + v * cv,
				base - u * cu + v * cv,
				normal_axis * s)


static func _box_edges(surface: SurfaceTool, core: Vector3, r: float,
		segments: int) -> void:
	## Twelve quarter-cylinders, one along each edge.
	for axis in 3:
		var along: Vector3 = AXES[axis]
		var u: Vector3 = AXES[CYCLE[axis][0]]
		var v: Vector3 = AXES[CYCLE[axis][1]]
		var cu: float = core[CYCLE[axis][0]]
		var cv: float = core[CYCLE[axis][1]]
		var extent: float = core[axis]
		if extent <= 1.0e-6:
			continue
		for su_index in 2:
			for sv_index in 2:
				var su := 1.0 if su_index == 0 else -1.0
				var sv := 1.0 if sv_index == 0 else -1.0
				var centre: Vector3 = u * (cu * su) + v * (cv * sv)
				for step in segments:
					var t0 := float(step) / float(segments) * (PI * 0.5)
					var t1 := float(step + 1) / float(segments) * (PI * 0.5)
					var n0: Vector3 = (u * (su * cos(t0)) + v * (sv * sin(t0)))
					var n1: Vector3 = (u * (su * cos(t1)) + v * (sv * sin(t1)))
					var a := centre + n0 * r - along * extent
					var b := centre + n0 * r + along * extent
					var c := centre + n1 * r + along * extent
					var d := centre + n1 * r - along * extent
					quad_smooth_auto(surface, [a, b, c, d], [n0, n0, n1, n1])


static func _box_corners(surface: SurfaceTool, core: Vector3, r: float,
		segments: int) -> void:
	## Eight spherical octants.
	for corner in 8:
		var sx := 1.0 if (corner & 1) == 0 else -1.0
		var sy := 1.0 if (corner & 2) == 0 else -1.0
		var sz := 1.0 if (corner & 4) == 0 else -1.0
		var centre := Vector3(core.x * sx, core.y * sy, core.z * sz)
		for ring in segments:
			var p0 := float(ring) / float(segments) * (PI * 0.5)
			var p1 := float(ring + 1) / float(segments) * (PI * 0.5)
			for seg in segments:
				var y0 := float(seg) / float(segments) * (PI * 0.5)
				var y1 := float(seg + 1) / float(segments) * (PI * 0.5)
				var n00 := _octant(p0, y0, sx, sy, sz)
				var n01 := _octant(p0, y1, sx, sy, sz)
				var n11 := _octant(p1, y1, sx, sy, sz)
				var n10 := _octant(p1, y0, sx, sy, sz)
				quad_smooth_auto(surface,
					[centre + n00 * r, centre + n01 * r,
						centre + n11 * r, centre + n10 * r],
					[n00, n01, n11, n10])


static func _octant(polar: float, azimuth: float, sx: float, sy: float,
		sz: float) -> Vector3:
	return Vector3(
		sx * sin(polar) * cos(azimuth),
		sy * cos(polar),
		sz * sin(polar) * sin(azimuth))


# --- surfaces of revolution -----------------------------------------------

static func profile_normals(points: Array, outward := true) -> Array:
	## Per-point 2D normals for a lathe profile, averaged across each joint.
	##
	## A profile is a list of `Vector2(radius, height)` read in one direction.
	## The normal of a segment is its direction turned ninety degrees; a
	## point's normal is the mean of the segments meeting there, which is what
	## makes a lathed fillet shade as a curve instead of as facets. Duplicate
	## a point in the profile to ask for a hard edge at it.
	var count := points.size()
	var normals: Array = []
	var segment: Array = []
	for index in count - 1:
		var a: Vector2 = points[index]
		var b: Vector2 = points[index + 1]
		var delta := b - a
		if delta.length_squared() < 1.0e-14:
			segment.append(Vector2(1.0, 0.0) if outward else Vector2(-1.0, 0.0))
			continue
		delta = delta.normalized()
		var n := Vector2(delta.y, -delta.x)
		segment.append(n if outward else -n)
	for index in count:
		var before: Vector2 = segment[maxi(index - 1, 0)] if not segment.is_empty() \
			else Vector2(1.0, 0.0)
		var after: Vector2 = segment[mini(index, segment.size() - 1)] \
			if not segment.is_empty() else Vector2(1.0, 0.0)
		var mean := before + after
		if mean.length_squared() < 1.0e-12:
			mean = after
		normals.append(mean.normalized())
	return normals


static func lathe(points: Array, normals: Array, segments: int,
		arc_from := 0.0, arc_to := TAU) -> ArrayMesh:
	## Spin a profile about the Y axis.
	##
	## The workhorse of the bowl: its inner running surface, the acrylic wall
	## standing on the rim, the light ring, the cradle's hoop and the toy
	## element's casing are all one profile each. Passing the normals in
	## rather than deriving them here is deliberate - the caller decides
	## which joints are creases and which are fillets, and that decision is
	## the whole difference between a moulded shell and a stack of cones.
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)

	for index in points.size() - 1:
		var pa: Vector2 = points[index]
		var pb: Vector2 = points[index + 1]
		var na: Vector2 = normals[index]
		var nb: Vector2 = normals[index + 1]
		for step in segments:
			var t0 := lerpf(arc_from, arc_to, float(step) / float(segments))
			var t1 := lerpf(arc_from, arc_to, float(step + 1) / float(segments))
			var c0 := cos(t0)
			var s0 := sin(t0)
			var c1 := cos(t1)
			var s1 := sin(t1)
			quad_smooth_auto(surface,
				[
					Vector3(pa.x * c0, pa.y, pa.x * s0),
					Vector3(pb.x * c0, pb.y, pb.x * s0),
					Vector3(pb.x * c1, pb.y, pb.x * s1),
					Vector3(pa.x * c1, pa.y, pa.x * s1),
				],
				[
					Vector3(na.x * c0, na.y, na.x * s0),
					Vector3(nb.x * c0, nb.y, nb.x * s0),
					Vector3(nb.x * c1, nb.y, nb.x * s1),
					Vector3(na.x * c1, na.y, na.x * s1),
				])

	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh


static func rounded_disc(radius: float, thickness: float, fillet: float,
		segments := 48, rounds := 4) -> ArrayMesh:
	## A puck with a filleted rim: hubs, caps, bases, the light ring's carrier.
	var r: float = clampf(fillet, 0.0, minf(radius, thickness * 0.5))
	var half := thickness * 0.5
	var points: Array = [Vector2(0.0, half)]
	var normals: Array = [Vector2(0.0, 1.0)]
	points.append(Vector2(radius - r, half))
	normals.append(Vector2(0.0, 1.0))
	for step in range(1, rounds + 1):
		var t := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(radius - r + r * sin(t), half - r + r * cos(t)))
		normals.append(Vector2(sin(t), cos(t)))
	points.append(Vector2(radius, -half + r))
	normals.append(Vector2(1.0, 0.0))
	for step in range(1, rounds + 1):
		var t := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(radius - r + r * cos(t), -half + r - r * sin(t)))
		normals.append(Vector2(cos(t), -sin(t)))
	points.append(Vector2(0.0, -half))
	normals.append(Vector2(0.0, -1.0))
	return lathe(points, normals, segments)


# --- swept sections -------------------------------------------------------
#
# ## Why a sweep has to be told which way is up
#
# The frame a cross-section is carried in has two axes. The lateral one a
# sweep can work out for itself, from the path. The vertical one it cannot,
# and every sweep here used to assume it was world up. For authored track that
# assumption is right and deliberate: a channel's walls stand up whatever the
# channel's gradient, so tilting the frame with the slope would light them as
# though they leaned.
#
# A banked bend is the case where it is wrong, and it is not a small wrong.
# The simulated curve rolls 27.7 degrees into its turn - the angle at which a
# marble at the design speed needs no sideways force from the wall at all - so
# its running surface is tilted and its walls are tilted with it. Swept with an
# upright section, the drawn floor is level where the solved floor is banked.
# The marbles are placed by the solver and not by the drawing, so they ride up
# the drawn wall, clip the drawn guard and hover over the drawn floor, and
# there is no lighting trick that hides a surface being in the wrong place.
#
# So the sweeps come in pairs. The `_framed` one takes an up vector per sample
# and is the real implementation; the plain one calls it with world up at every
# sample, and is what every existing caller gets.


static func world_ups(count: int) -> Array:
	## `count` copies of world up: the frame an unbanked sweep runs in.
	var ups: Array = []
	for _index in count:
		ups.append(Vector3.UP)
	return ups


static func lateral_frame(path: Array, ups: Array, index: int) -> Vector3:
	## The lateral axis at one sample, square to both the path and its up.
	##
	## `up.cross(tangent)`, and the order of the two is load-bearing: the other
	## order names the same axis pointing the other way, which mirrors every
	## cross-section in the machine and turns a channel inside out.
	##
	## With `up` equal to world up this is exactly the rule the unbanked sweeps
	## have always used - the path's horizontal direction, turned ninety
	## degrees - because crossing with world up annihilates the tangent's
	## vertical component, so projecting the tangent flat first would change
	## nothing. That equivalence is the whole reason the plain sweeps can
	## delegate here and still hand back the mesh they handed back before.
	var before: Vector3 = path[maxi(index - 1, 0)]
	var after: Vector3 = path[mini(index + 1, path.size() - 1)]
	var up: Vector3 = ups[index]
	var side := up.cross(after - before)
	if side.length_squared() < 1.0e-12:
		# The path stalls or doubles back here and has no tangent to speak of.
		# Any axis square to `up` will do; the candidates are tried in a fixed
		# order so the choice is a property of the input and nothing else.
		side = up.cross(Vector3(0.0, 0.0, 1.0))
		if side.length_squared() < 1.0e-12:
			side = up.cross(Vector3(1.0, 0.0, 0.0))
	return side.normalized()


static func lateral_frames(path: Array, ups: Array) -> Array:
	## `lateral_frame` at every sample of a path.
	var frames: Array = []
	for index in path.size():
		frames.append(lateral_frame(path, ups, index))
	return frames


static func sweep_profiles(path: Array, sections: Array, normals: Array,
		cap_ends := true) -> ArrayMesh:
	## `sweep`, with its own cross-section at every sample.
	##
	## What the track is actually built with. A channel that keeps one width
	## down its whole length is a extrusion, and an extrusion is the thing the
	## V1.1 report was measured as: a straight pull with a square lip and
	## zero curvature shading. A channel that widens where the course opens
	## and closes where it narrows is a moulded component, and it is also the
	## only version that is guaranteed to have something under every racer -
	## the width is the course's own clear span, not a number chosen to look
	## right.
	##
	## Every section must have the same point count, which they do when they
	## come from `channel_section` with the same `rounds`.
	return sweep_profiles_framed(
		path, world_ups(path.size()), sections, normals, cap_ends)


static func sweep_profiles_framed(path: Array, ups: Array, sections: Array,
		normals: Array, cap_ends := true) -> ArrayMesh:
	## `sweep_profiles`, banked: one up vector per sample rather than world up.
	##
	## `ups` must be as long as `path`. It need not be exactly square to the
	## path: the lateral axis is derived from the two, so it comes out square
	## to the up whatever the tangent does, and a frame handed over by a solver
	## whose samples are a finite distance apart stays orthonormal here.
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)

	var frames := lateral_frames(path, ups)
	for index in path.size() - 1:
		var c0: Vector3 = path[index]
		var c1: Vector3 = path[index + 1]
		var l0: Vector3 = frames[index]
		var l1: Vector3 = frames[index + 1]
		var u0: Vector3 = ups[index]
		var u1: Vector3 = ups[index + 1]
		var s0: Array = sections[index]
		var s1: Array = sections[index + 1]
		var n0: Array = normals[index]
		var n1: Array = normals[index + 1]
		for at in mini(s0.size(), s1.size()) - 1:
			var a0: Vector2 = s0[at]
			var b0: Vector2 = s0[at + 1]
			var a1: Vector2 = s1[at]
			var b1: Vector2 = s1[at + 1]
			var na0: Vector2 = n0[at]
			var nb0: Vector2 = n0[at + 1]
			var na1: Vector2 = n1[at]
			var nb1: Vector2 = n1[at + 1]
			quad_smooth_auto(surface,
				[
					c0 + l0 * a0.x + u0 * a0.y,
					c1 + l1 * a1.x + u1 * a1.y,
					c1 + l1 * b1.x + u1 * b1.y,
					c0 + l0 * b0.x + u0 * b0.y,
				],
				[
					l0 * na0.x + u0 * na0.y,
					l1 * na1.x + u1 * na1.y,
					l1 * nb1.x + u1 * nb1.y,
					l0 * nb0.x + u0 * nb0.y,
				])

	if cap_ends and path.size() >= 2:
		_cap(surface, path[0], frames[0], ups[0], sections[0], -1.0)
		_cap(surface, path[path.size() - 1], frames[frames.size() - 1],
			ups[ups.size() - 1], sections[sections.size() - 1], 1.0)

	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh


static func sweep(path: Array, section: Array, section_normals: Array,
		cap_ends := true) -> ArrayMesh:
	## Carry a cross-section along a path of world-space centres.
	##
	## This is how the curved track becomes a manufactured component rather
	## than a slab: one rounded channel profile, swept. The frame at each
	## sample is the path's own horizontal direction with world up, which is
	## the same rule `neon_scene.gd` takes its side normals under and for the
	## same reason - a track's walls stand up whatever the track's gradient,
	## so tilting the frame with the slope would light them as though they
	## leaned. Track that is genuinely banked wants `sweep_framed` instead.
	##
	## `section` is a list of `Vector2(lateral, vertical)` in world units,
	## read left to right across the channel; `section_normals` is its
	## outward normal per point, in the same frame.
	return sweep_framed(
		path, world_ups(path.size()), section, section_normals, cap_ends)


static func sweep_framed(path: Array, ups: Array, section: Array,
		section_normals: Array, cap_ends := true) -> ArrayMesh:
	## `sweep`, banked: one up vector per sample rather than world up.
	##
	## The section's `y` is measured along the supplied up and its `x` along
	## the lateral axis that falls out of it, so one authored cross-section
	## serves level track and banked track alike and the two meet at a joint
	## without a step in the running surface.
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)

	var frames := lateral_frames(path, ups)

	for index in path.size() - 1:
		var c0: Vector3 = path[index]
		var c1: Vector3 = path[index + 1]
		var l0: Vector3 = frames[index]
		var l1: Vector3 = frames[index + 1]
		var u0: Vector3 = ups[index]
		var u1: Vector3 = ups[index + 1]
		for at in section.size() - 1:
			var sa: Vector2 = section[at]
			var sb: Vector2 = section[at + 1]
			var na: Vector2 = section_normals[at]
			var nb: Vector2 = section_normals[at + 1]
			quad_smooth_auto(surface,
				[
					c0 + l0 * sa.x + u0 * sa.y,
					c1 + l1 * sa.x + u1 * sa.y,
					c1 + l1 * sb.x + u1 * sb.y,
					c0 + l0 * sb.x + u0 * sb.y,
				],
				[
					l0 * na.x + u0 * na.y,
					l1 * na.x + u1 * na.y,
					l1 * nb.x + u1 * nb.y,
					l0 * nb.x + u0 * nb.y,
				])

	if cap_ends and path.size() >= 2:
		_cap(surface, path[0], frames[0], ups[0], section, -1.0)
		_cap(surface, path[path.size() - 1], frames[frames.size() - 1],
			ups[ups.size() - 1], section, 1.0)

	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh


static func _cap(surface: SurfaceTool, centre: Vector3, lateral: Vector3,
		up: Vector3, section: Array, facing: float) -> void:
	## Close a swept solid with a fan from the section's own midpoint.
	var forward := lateral.cross(up).normalized() * facing
	var mid := Vector2.ZERO
	for raw in section:
		mid += raw as Vector2
	mid /= float(maxi(section.size(), 1))
	var hub := centre + lateral * mid.x + up * mid.y
	for at in section.size() - 1:
		var sa: Vector2 = section[at]
		var sb: Vector2 = section[at + 1]
		quad_auto(surface,
			hub,
			centre + lateral * sa.x + up * sa.y,
			centre + lateral * sb.x + up * sb.y,
			hub,
			forward)


static func tube(path: Array, radius: float, sides := 12) -> ArrayMesh:
	## A round bar along a path: rails, hand-rails, hoops, pipework.
	##
	## Rounded stock rather than square is most of what separates a toy's
	## hardware from a factory's, and a tube costs the same as the box it
	## replaces.
	return tube_framed(path, world_ups(path.size()), radius, sides)


static func tube_framed(path: Array, ups: Array, radius: float,
		sides := 12) -> ArrayMesh:
	## `tube`, banked.
	##
	## A round bar is rotationally symmetric, so the frame changes nothing
	## about its shape - but it changes where it *is*, because a lip, an edge
	## light or a guard cap is only ever drawn on an offset path, and that
	## path was built in the channel's frame. Rolling the two apart is how a
	## neon rope ends up inside the channel it is meant to run outboard of.
	var section: Array = []
	var normals: Array = []
	for step in sides + 1:
		var t := float(step) / float(sides) * TAU
		var n := Vector2(cos(t), sin(t))
		normals.append(n)
		section.append(n * radius)
	return sweep_framed(path, ups, section, normals, false)

static func arc_path(centre: Vector3, radius: float, from_angle: float,
		to_angle: float, height_from: float, height_to: float,
		steps := 24) -> Array:
	## A horizontal arc with an even rise along it, as a path for `sweep`.
	var path: Array = []
	for step in steps + 1:
		var t := float(step) / float(steps)
		var angle := lerpf(from_angle, to_angle, t)
		path.append(Vector3(
			centre.x + radius * cos(angle),
			lerpf(height_from, height_to, t),
			centre.z + radius * sin(angle)))
	return path


# --- cross-sections -------------------------------------------------------

static func beam_section(half_width: float, height: float, fillet: float,
		rounds := 4) -> Array:
	## A rounded rectangular beam, as `[points, normals]` for `sweep`.
	##
	## The fascia under a track. The reference builds every one of its beams
	## as a thin bright top lip over a much deeper warm fascia - about five
	## pixels of silver over ten of brass on a forty-pixel deck - and that
	## split is where a third of its warm coverage comes from. A single-
	## material channel cannot do it; this is the second material.
	var f: float = clampf(fillet, 0.005, minf(half_width * 0.9, height * 0.45))
	var half := height * 0.5
	var points: Array = []
	var normals: Array = []

	points.append(Vector2(-half_width, half - f))
	normals.append(Vector2(-1.0, 0.0))
	for step in range(1, rounds + 1):
		var a := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			-half_width + f - f * cos(a), half - f + f * sin(a)))
		normals.append(Vector2(-cos(a), sin(a)))
	points.append(Vector2(half_width - f, half))
	normals.append(Vector2(0.0, 1.0))
	for step in range(1, rounds + 1):
		var a := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			half_width - f + f * sin(a), half - f + f * cos(a)))
		normals.append(Vector2(sin(a), cos(a)))
	points.append(Vector2(half_width, -half + f))
	normals.append(Vector2(1.0, 0.0))
	for step in range(1, rounds + 1):
		var a := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			half_width - f + f * cos(a), -half + f - f * sin(a)))
		normals.append(Vector2(cos(a), -sin(a)))
	points.append(Vector2(-half_width + f, -half))
	normals.append(Vector2(0.0, -1.0))
	for step in range(1, rounds + 1):
		var a := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			-half_width + f - f * sin(a), -half + f - f * cos(a)))
		normals.append(Vector2(-sin(a), -cos(a)))
	points.append(Vector2(-half_width, half - f))
	normals.append(Vector2(-1.0, 0.0))

	return [points, normals]


static func channel_section(half_width: float, floor_drop: float,
		wall_height: float, fillet: float, rounds := 4) -> Array:
	## A rounded running channel, as `[points, normals]` for `sweep`.
	##
	## The brief's cross-section rule, made concrete: a pearl channel with a
	## radiused floor-to-wall transition, walls that turn over at the top
	## instead of ending in an edge, and a shell that wraps under. Read left
	## to right, starting outside the left wall and finishing outside the
	## right one, so one sweep produces the whole component - running surface,
	## walls, outer flanks and underside - as a single closed solid.
	var f: float = clampf(fillet, 0.01, minf(half_width * 0.45, wall_height * 0.9))
	var points: Array = []
	var normals: Array = []

	# The underside, left to right, with its own corner rounds.
	points.append(Vector2(-half_width, -floor_drop + f))
	normals.append(Vector2(-1.0, 0.0))
	for step in range(1, rounds + 1):
		var t := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			-half_width + f - f * cos(t), -floor_drop + f - f * sin(t)))
		normals.append(Vector2(-cos(t), -sin(t)))
	points.append(Vector2(half_width - f, -floor_drop))
	normals.append(Vector2(0.0, -1.0))
	for step in range(1, rounds + 1):
		var t := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			half_width - f + f * sin(t), -floor_drop + f - f * cos(t)))
		normals.append(Vector2(sin(t), -cos(t)))

	# Up the right flank, over the top of the right wall.
	points.append(Vector2(half_width, wall_height - f))
	normals.append(Vector2(1.0, 0.0))
	for step in range(1, rounds + 1):
		var t := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			half_width - f + f * cos(t), wall_height - f + f * sin(t)))
		normals.append(Vector2(cos(t), sin(t)))

	# Down the inside of the right wall to the channel floor, radiused.
	points.append(Vector2(half_width - f, f))
	normals.append(Vector2(-1.0, 0.0))
	for step in range(1, rounds + 1):
		var t := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			half_width - f - f * sin(t), f - f * cos(t)))
		normals.append(Vector2(-sin(t), cos(t)))

	# Across the running surface and up the inside of the left wall.
	points.append(Vector2(-half_width + f, 0.0))
	normals.append(Vector2(0.0, 1.0))
	for step in range(1, rounds + 1):
		var t := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			-half_width + f - f * sin(t), f - f * cos(t)))
		normals.append(Vector2(sin(t), cos(t)))
	points.append(Vector2(-half_width + f, wall_height - f))
	normals.append(Vector2(1.0, 0.0))
	for step in range(1, rounds + 1):
		var t := float(step) / float(rounds) * (PI * 0.5)
		points.append(Vector2(
			-half_width + f - f * cos(t), wall_height - f + f * sin(t)))
		normals.append(Vector2(-cos(t), sin(t)))
	points.append(Vector2(-half_width, wall_height - f))
	normals.append(Vector2(-1.0, 0.0))

	return [points, normals]
