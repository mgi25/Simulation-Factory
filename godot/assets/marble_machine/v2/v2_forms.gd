extends RefCounted

## V2 form toolkit: the shapes the prior lab could not make.
##
## `toy_geometry.gd` gives rounded primitives and `lab_forms.gd` gives the
## medium-scale parts vocabulary. Both stay as they are. What neither can do is
## the single thing the V2 brief makes mandatory for the signature track:
##
## **banking.** `toy_geometry.sweep` builds its frame from the path's
## *horizontal* direction and world up, which is correct for a guard rail that
## must stand upright regardless of gradient, and wrong for a channel that has
## to roll into its turns. A track that does not bank reads as a gutter laid on
## the ground; a track that banks reads as something a marble was designed to
## run through at speed. Everything else here exists to serve that: rolled
## frames, rolled offset paths, and a basis per sample so ribs and lights can
## be placed *on* the rolled section instead of beside it.
##
## The rest is shells - closed lathe profiles with real wall thickness, so a
## transparent bowl has an edge you can see rather than a zero-width membrane -
## and the two environment builders, which are here rather than in the world
## file because they are geometry rather than art direction.
##
## Determinism: every builder is a pure function of its arguments. The rock
## builders take an integer seed and hash it arithmetically; no RNG is
## constructed and no clock is read, so two renders are byte-identical.

const Geometry := preload("res://scripts/toy_geometry.gd")


# --- banked frames --------------------------------------------------------

static func flat_tangents(path: Array) -> Array:
	## Unit forward at each sample, in full 3D including the gradient.
	var out: Array = []
	for index in path.size():
		var before: Vector3 = path[maxi(index - 1, 0)]
		var after: Vector3 = path[mini(index + 1, path.size() - 1)]
		var forward: Vector3 = after - before
		if forward.length_squared() < 1.0e-12:
			forward = Vector3(0.0, 0.0, 1.0)
		out.append(forward.normalized())
	return out


static func curvature(path: Array) -> Array:
	## Signed horizontal curvature per sample: positive turns left.
	##
	## Measured in the horizontal plane only. A track that dives has a large
	## 3D curvature and should not bank for it - banking answers lateral
	## acceleration, and lateral acceleration is a plan-view quantity.
	var out: Array = []
	for index in path.size():
		var a: Vector3 = path[maxi(index - 1, 0)]
		var b: Vector3 = path[index]
		var c: Vector3 = path[mini(index + 1, path.size() - 1)]
		var v0 := Vector3(b.x - a.x, 0.0, b.z - a.z)
		var v1 := Vector3(c.x - b.x, 0.0, c.z - b.z)
		var l0 := v0.length()
		var l1 := v1.length()
		if l0 < 1.0e-6 or l1 < 1.0e-6:
			out.append(0.0)
			continue
		v0 /= l0
		v1 /= l1
		# y component of v0 x v1: positive when the heading swings to -X,
		# which for a +Z heading is a left turn.
		var turn := v0.z * v1.x - v0.x * v1.z
		out.append(-turn / maxf((l0 + l1) * 0.5, 1.0e-4))
	return out


static func smooth_series(values: Array, passes := 3) -> Array:
	## Box-blur a per-sample series so a bank angle has no step in it.
	##
	## Curvature computed from three samples is noisy at the joints between
	## spline spans, and a bank angle that steps is worse than no bank at all
	## - the highlight running along the lip kinks at every step, which is
	## precisely the "generated, not moulded" tell the brief bans.
	var current: Array = values.duplicate()
	for _pass in passes:
		var next: Array = []
		for index in current.size():
			var a: float = current[maxi(index - 1, 0)]
			var b: float = current[index]
			var c: float = current[mini(index + 1, current.size() - 1)]
			next.append((a + b + c) / 3.0)
		current = next
	return current


static func auto_bank(path: Array, gain: float, max_degrees: float,
		ease_ends := 6) -> Array:
	## A bank angle per sample, from the path's own curvature.
	##
	## `gain` converts curvature into radians of roll; `max_degrees` clamps it
	## so a tight hook does not roll past the point where the channel's far
	## lip occludes its own floor from the hero camera. The ends are eased to
	## zero so a banked track meets a level module square.
	var limit := deg_to_rad(max_degrees)
	var raw: Array = []
	for k in curvature(path):
		raw.append(clampf(float(k) * gain, -limit, limit))
	var banks: Array = smooth_series(raw, 4)
	var count := banks.size()
	for index in count:
		var from_start: float = float(index) / float(maxi(ease_ends, 1))
		var from_end: float = float(count - 1 - index) / float(maxi(ease_ends, 1))
		var ease: float = clampf(minf(from_start, from_end), 0.0, 1.0)
		banks[index] = float(banks[index]) * smoothstep(0.0, 1.0, ease)
	return banks


static func banked_basis(path: Array, banks: Array, index: int) -> Basis:
	## The rolled frame at one sample: X lateral, Y up, Z forward.
	##
	## `lateral` points to the track's own left. Section coordinates are read
	## in this basis, which is what makes a bank a roll of the whole
	## cross-section rather than a shear of it.
	var tangents := flat_tangents(path)
	var forward: Vector3 = tangents[clampi(index, 0, tangents.size() - 1)]
	var side := Vector3(forward.z, 0.0, -forward.x)
	if side.length_squared() < 1.0e-12:
		side = Vector3(1.0, 0.0, 0.0)
	side = side.normalized()
	var up := forward.cross(side).normalized()
	var roll: float = float(banks[clampi(index, 0, banks.size() - 1)]) \
		if not banks.is_empty() else 0.0
	var lateral := side * cos(roll) + up * sin(roll)
	var rolled_up := up * cos(roll) - side * sin(roll)
	return Basis(lateral, rolled_up, forward)


static func _frames(path: Array, banks: Array) -> Array:
	var out: Array = []
	for index in path.size():
		out.append(banked_basis(path, banks, index))
	return out


static func banked_sweep(path: Array, sections: Array, normals: Array,
		banks: Array, cap_ends := true) -> ArrayMesh:
	## Carry a cross-section along a path, rolled by `banks` at every sample.
	##
	## `sections[i]` is a list of `Vector2(lateral, vertical)` in the rolled
	## frame and `normals[i]` its outward normal per point. Passing a section
	## per sample rather than one for the whole run is what lets the channel
	## widen at the entry throat and close at the exit - a constant section is
	## an extrusion, and an extrusion is what the brief calls procedural.
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var frames := _frames(path, banks)

	for index in path.size() - 1:
		var c0: Vector3 = path[index]
		var c1: Vector3 = path[index + 1]
		var f0: Basis = frames[index]
		var f1: Basis = frames[index + 1]
		var s0: Array = sections[mini(index, sections.size() - 1)]
		var s1: Array = sections[mini(index + 1, sections.size() - 1)]
		var n0: Array = normals[mini(index, normals.size() - 1)]
		var n1: Array = normals[mini(index + 1, normals.size() - 1)]
		for at in mini(s0.size(), s1.size()) - 1:
			var a0: Vector2 = s0[at]
			var b0: Vector2 = s0[at + 1]
			var a1: Vector2 = s1[at]
			var b1: Vector2 = s1[at + 1]
			var na0: Vector2 = n0[at]
			var nb0: Vector2 = n0[at + 1]
			var na1: Vector2 = n1[at]
			var nb1: Vector2 = n1[at + 1]
			Geometry.quad_smooth_auto(surface,
				[
					c0 + f0.x * a0.x + f0.y * a0.y,
					c1 + f1.x * a1.x + f1.y * a1.y,
					c1 + f1.x * b1.x + f1.y * b1.y,
					c0 + f0.x * b0.x + f0.y * b0.y,
				],
				[
					f0.x * na0.x + f0.y * na0.y,
					f1.x * na1.x + f1.y * na1.y,
					f1.x * nb1.x + f1.y * nb1.y,
					f0.x * nb0.x + f0.y * nb0.y,
				])

	if cap_ends and path.size() >= 2:
		_cap(surface, path[0], frames[0], sections[0], -1.0)
		_cap(surface, path[path.size() - 1], frames[frames.size() - 1],
			sections[sections.size() - 1], 1.0)

	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh


static func _cap(surface: SurfaceTool, centre: Vector3, frame: Basis,
		section: Array, facing: float) -> void:
	## Close a swept solid with a fan from the section's own midpoint.
	var forward: Vector3 = frame.z * facing
	var mid := Vector2.ZERO
	for raw in section:
		mid += raw as Vector2
	mid /= float(maxi(section.size(), 1))
	var hub := centre + frame.x * mid.x + frame.y * mid.y
	for at in section.size() - 1:
		var sa: Vector2 = section[at]
		var sb: Vector2 = section[at + 1]
		var pa := centre + frame.x * sa.x + frame.y * sa.y
		var pb := centre + frame.x * sb.x + frame.y * sb.y
		if facing > 0.0:
			Geometry.quad_smooth_auto(surface, [hub, pa, pb, pb],
				[forward, forward, forward, forward])
		else:
			Geometry.quad_smooth_auto(surface, [hub, pb, pa, pa],
				[forward, forward, forward, forward])


static func banked_offset(path: Array, banks: Array, lateral: float,
		vertical: float) -> Array:
	## The same path, shifted in each sample's *rolled* frame.
	##
	## An edge light or a guard wall offset in world axes drifts off a banked
	## channel by the sine of the roll; offset in the rolled frame it stays
	## welded to the lip it belongs to.
	var frames := _frames(path, banks)
	var out: Array = []
	for index in path.size():
		var frame: Basis = frames[index]
		out.append(path[index] + frame.x * lateral + frame.y * vertical)
	return out


static func resample(path: Array, count: int) -> Array:
	## `count` samples at equal *arc length* along a polyline.
	##
	## A Catmull-Rom spline sampled at equal parameter bunches its points
	## where the control polygon is dense, and a rib placed every N samples
	## then lands unevenly. Equal arc length makes "every 1.4 units" mean
	## what it says.
	if path.size() < 2 or count < 2:
		return path.duplicate()
	var lengths: Array = [0.0]
	var total := 0.0
	for index in path.size() - 1:
		total += (path[index + 1] as Vector3).distance_to(path[index])
		lengths.append(total)
	var out: Array = []
	var cursor := 0
	for step in count:
		var want: float = total * float(step) / float(count - 1)
		while cursor < lengths.size() - 2 and float(lengths[cursor + 1]) < want:
			cursor += 1
		var a: float = lengths[cursor]
		var b: float = lengths[cursor + 1]
		var t: float = 0.0 if b - a < 1.0e-9 else (want - a) / (b - a)
		out.append((path[cursor] as Vector3).lerp(path[cursor + 1], t))
	return out


static func path_length(path: Array) -> float:
	var total := 0.0
	for index in path.size() - 1:
		total += (path[index + 1] as Vector3).distance_to(path[index])
	return total


# --- section builders -----------------------------------------------------

static func ensure_ccw(points: Array) -> Array:
	## A closed 2D section, wound so that `(dy, -dx)` faces outward.
	##
	## Sections are authored as a readable walk around the profile, and half
	## of them come out clockwise simply because that was the natural
	## direction to describe them in. Winding decides which way the normals
	## point, and normals decide which way the triangles face, so it is fixed
	## once here rather than being reasoned about at every call site.
	var area := 0.0
	for index in points.size() - 1:
		var a: Vector2 = points[index]
		var b: Vector2 = points[index + 1]
		area += a.x * b.y - b.x * a.y
	if area >= 0.0:
		return points.duplicate()
	var out: Array = []
	for index in range(points.size() - 1, -1, -1):
		out.append(points[index])
	return out


static func mirror_close(half: Array) -> Array:
	## A symmetric closed section from the half that was authored.
	##
	## `half` runs from one point on the centreline to another; the return
	## walks it, then walks its mirror image back, so the seam falls on the
	## centreline where both neighbours exist and the joint gets a properly
	## averaged normal instead of a crease.
	var out: Array = half.duplicate()
	for index in range(half.size() - 2, -1, -1):
		var point: Vector2 = half[index]
		out.append(Vector2(-point.x, point.y))
	return out


static func section_normals(points: Array) -> Array:
	## Outward normals for a hand-built section, averaged at each joint.
	##
	## The same rule as `profile_normals`, in the section's own 2D frame:
	## duplicate a point to ask for a crease, leave it single for a fillet.
	var count := points.size()
	var segments: Array = []
	for index in count - 1:
		var delta: Vector2 = (points[index + 1] as Vector2) - (points[index] as Vector2)
		if delta.length_squared() < 1.0e-14:
			segments.append(Vector2(0.0, 1.0))
			continue
		delta = delta.normalized()
		segments.append(Vector2(delta.y, -delta.x))
	var out: Array = []
	for index in count:
		var before: Vector2 = segments[maxi(index - 1, 0)]
		var after: Vector2 = segments[mini(index, segments.size() - 1)]
		var mean := before + after
		if mean.length_squared() < 1.0e-12:
			mean = after
		out.append(mean.normalized())
	return out


static func scaled_sections(section: Array, normals: Array, count: int,
		scale_curve: Array) -> Array:
	## One section per sample, laterally scaled by a per-sample factor.
	##
	## Returns `[sections, normals]`. Lateral only: a channel that also grew
	## vertically would change its own floor depth, and the marble sits on
	## that floor.
	var sections: Array = []
	var out_normals: Array = []
	for index in count:
		var factor: float = float(scale_curve[mini(index, scale_curve.size() - 1)])
		var scaled: Array = []
		for point in section:
			scaled.append(Vector2((point as Vector2).x * factor, (point as Vector2).y))
		sections.append(scaled)
		out_normals.append(normals)
	return [sections, out_normals]


# --- shells ---------------------------------------------------------------

static func shell_lathe(outer: Array, thickness: float, segments: int,
		close_top := true) -> ArrayMesh:
	## A lathed surface given real wall thickness, as one closed solid.
	##
	## The prior bowl's acrylic wall was a single-sided lathe, which has no
	## edge: at the rim it ends in a zero-width line and the eye reads it as
	## film rather than as cast plastic. Walking the profile out and back with
	## an inward offset gives the rim a visible thickness, and thickness is
	## the entire difference between a soap bubble and a moulded guard.
	var profile: Array = outer.duplicate()
	var reversed: Array = []
	for index in range(outer.size() - 1, -1, -1):
		var point: Vector2 = outer[index]
		var before: Vector2 = outer[maxi(index - 1, 0)]
		var after: Vector2 = outer[mini(index + 1, outer.size() - 1)]
		var tangent: Vector2 = after - before
		if tangent.length_squared() < 1.0e-14:
			tangent = Vector2(0.0, 1.0)
		tangent = tangent.normalized()
		var inward := Vector2(-tangent.y, tangent.x)
		reversed.append(point + inward * thickness)
	profile.append_array(reversed)
	if close_top:
		profile.append(outer[0])
	return Geometry.lathe(profile, Geometry.profile_normals(profile), segments)


static func dish_profile(rim_radius: float, drain_radius: float, depth: float,
		rounds := 14) -> Array:
	## A bowl running surface: shallow at the rim, steep at the drain.
	##
	## A raised cosine in *radius*, so the shoulder where the field circulates
	## stays close to horizontal and catches the key across its whole width,
	## and the fall only begins near the throat. A hemisphere would put the
	## marbles on a wall the camera sees edge-on.
	var points: Array = []
	for step in rounds + 1:
		var t := float(step) / float(rounds)
		var radius: float = lerpf(drain_radius, rim_radius, t)
		points.append(Vector2(radius, -depth * (0.5 + 0.5 * cos(t * PI))))
	return points


# --- environment geometry -------------------------------------------------

static func _hash01(seed_value: int) -> float:
	## A deterministic pseudo-random in [0,1) from an integer.
	var x := (seed_value * 1103515245 + 12345) & 0x7FFFFFFF
	x = (x ^ (x >> 13)) * 1274126177
	return float((x ^ (x >> 16)) & 0xFFFF) / 65536.0


static func rock_mass(height: float, base_radius: float, seed_value: int,
		facets := 11, tiers := 7) -> ArrayMesh:
	## A cliff block: a faceted, tapering, irregular prism.
	##
	## Cliffs are silhouette and nothing else - they sit four to twelve stops
	## under the machine and are read entirely by their outline against the
	## sky. So they are built cheap and angular on purpose: a smooth lathed
	## hill reads as a dune, and hard facets at this scale read as rock even
	## when every one of them is flat-shaded.
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)

	var rings: Array = []
	for tier in tiers + 1:
		var t := float(tier) / float(tiers)
		var taper: float = 1.0 - 0.72 * t * t
		var y: float = height * t
		var ring: Array = []
		for facet in facets:
			var angle := TAU * float(facet) / float(facets)
			var jitter := 0.62 + 0.55 * _hash01(seed_value * 131 + tier * 17 + facet)
			var lift := (_hash01(seed_value * 71 + facet * 29 + tier * 5) - 0.5) \
				* height * 0.08
			var radius: float = base_radius * taper * jitter
			ring.append(Vector3(cos(angle) * radius, y + lift, sin(angle) * radius))
		rings.append(ring)

	for tier in tiers:
		var lower: Array = rings[tier]
		var upper: Array = rings[tier + 1]
		for facet in facets:
			var next := (facet + 1) % facets
			var a: Vector3 = lower[facet]
			var b: Vector3 = upper[facet]
			var c: Vector3 = upper[next]
			var d: Vector3 = lower[next]
			# Flat-shaded on purpose: a faceted cliff is the read, and the
			# outward direction is simply "away from the axis at this height".
			var mid := (a + b + c + d) * 0.25
			var outward := Vector3(mid.x, 0.0, mid.z)
			if outward.length_squared() < 1.0e-8:
				outward = Vector3(1.0, 0.0, 0.0)
			Geometry.quad_auto(surface, a, b, c, d,
				(outward.normalized() + Vector3.UP * 0.35).normalized())

	var crown: Array = rings[tiers]
	var peak := Vector3(0.0, height * 1.06, 0.0)
	for facet in facets:
		var next := (facet + 1) % facets
		var a: Vector3 = crown[facet]
		var d: Vector3 = crown[next]
		var mid := (a + d) * 0.5
		var outward := Vector3(mid.x, 0.0, mid.z)
		if outward.length_squared() < 1.0e-8:
			outward = Vector3(1.0, 0.0, 0.0)
		Geometry.quad_auto(surface, a, peak, peak, d,
			(outward.normalized() * 0.5 + Vector3.UP).normalized())

	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh


static func ridge_wall(length: float, height: float, depth: float,
		seed_value: int, teeth := 9) -> ArrayMesh:
	## A far ridge line: a jagged slab, seen only as a horizon shape.
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var half_depth := depth * 0.5
	var previous := Vector3(-length * 0.5, 0.0, 0.0)
	var previous_top := previous + Vector3.UP * height * 0.4
	for tooth in teeth:
		var t := float(tooth + 1) / float(teeth)
		var x: float = lerpf(-length * 0.5, length * 0.5, t)
		var peak: float = height * (0.34 + 0.66 * _hash01(seed_value * 53 + tooth * 11))
		var base := Vector3(x, 0.0, 0.0)
		var top := Vector3(x, peak, 0.0)
		for side in [-half_depth, half_depth]:
			var offset := Vector3(0.0, 0.0, side)
			Geometry.quad_auto(surface, previous + offset, previous_top + offset,
				top + offset, base + offset,
				Vector3(0.0, 0.0, signf(side)))
		Geometry.quad_auto(surface,
			previous_top + Vector3(0.0, 0.0, -half_depth),
			previous_top + Vector3(0.0, 0.0, half_depth),
			top + Vector3(0.0, 0.0, half_depth),
			top + Vector3(0.0, 0.0, -half_depth),
			Vector3.UP)
		previous = base
		previous_top = top
	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh
