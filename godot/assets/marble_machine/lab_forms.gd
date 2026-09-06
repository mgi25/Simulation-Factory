extends RefCounted

## Authoring forms: the shapes a designed toy module is made of, on top of the
## rounded primitives in `toy_geometry.gd`.
##
## `toy_geometry` answers "how do I build a filleted box, a lathe, a sweep".
## This file answers "what are the parts a premium playset is assembled from" -
## columns with collars, cross-braced bays, flowing spline track, spoked hubs,
## guard hoops, bolt rings, equipment racks. It is the medium-scale layer that
## every previous prototype was missing, expressed once so four modules can
## share it and a fifth can be added without inventing new vocabulary.
##
## ## Why the medium layer needed its own file
##
## The style-lock render failed at framing rather than at surface: it was one
## bowl at macro distance, and at that distance a module has nothing around it
## to establish scale. Pulling the camera back to see four modules at once is
## only an improvement if the space between them is *designed*. Empty air
## between two beautiful parts reads as an unfinished scene. Collars, braces,
## belts and racks are what fill that space, and they are what the reference
## concept is dense with - its tower is perhaps a third track and two thirds
## structure by area.
##
## ## Determinism
##
## Every builder is a pure function of its arguments. Nothing reads a clock or
## randomises: where a scattering of parts is wanted, the caller passes an
## index and the placement is arithmetic on it. Two renders of one scene
## produce byte-identical meshes.

const Geometry := preload("res://scripts/toy_geometry.gd")


# --- node plumbing --------------------------------------------------------

static func mesh_node(mesh: Mesh, material: Material, node_name: String,
		cast_shadow := true) -> MeshInstance3D:
	## One mesh, one material, named so a scene tree can be read.
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.material_override = material
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if cast_shadow \
		else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return node


static func placed(node: Node3D, at: Vector3, rotation_y := 0.0) -> Node3D:
	## Position and yaw in one call, because almost every part wants both.
	node.position = at
	node.rotation.y = rotation_y
	return node


static func ring_positions(count: int, radius: float, phase := 0.0,
		height := 0.0) -> Array:
	## `count` points evenly around Y, as world offsets. Hardware placement.
	var points: Array = []
	for index in count:
		var angle := phase + TAU * float(index) / float(maxi(count, 1))
		points.append(Vector3(cos(angle) * radius, height, sin(angle) * radius))
	return points


# --- protected volumes ----------------------------------------------------
#
# A module can claim the air it needs to be *seen* in, and the frame builders
# read that claim before they place a member.
#
# The rule this expresses is the one the first hero frame broke: a support
# system built only from "is there room for it" clearances will happily put a
# diagonal straight across the mouth of a bowl, because there genuinely is
# room - the bar misses every surface. What it does not miss is the shot. A
# module's action volume is therefore declared once, by the module, in the
# same units as everything else, and the tower and the chutes route around it.
#
# The volume is a capped vertical cylinder because every module here is a
# lathe and the camera orbits: a box would have to be re-authored for each
# azimuth and a cylinder is right from all of them.

static func clearance(centre: Vector3, radius: float, bottom: float,
		top: float, owner := "") -> Dictionary:
	## One protected cylinder, in world units.
	##
	## `owner` names the node whose own parts are allowed inside it - a bowl
	## is not intruding on itself - and is only read by the audit.
	return {
		"x": centre.x, "z": centre.z,
		"radius": radius, "bottom": bottom, "top": top, "owner": owner,
	}


static func point_clears(point: Vector3, volume: Dictionary) -> bool:
	if point.y < float(volume["bottom"]) or point.y > float(volume["top"]):
		return true
	var dx := point.x - float(volume["x"])
	var dz := point.z - float(volume["z"])
	var radius := float(volume["radius"])
	return dx * dx + dz * dz >= radius * radius


static func segment_clears(from: Vector3, to: Vector3,
		volume: Dictionary) -> bool:
	## True when no part of the segment is inside the cylinder.
	##
	## Solved rather than sampled. Sampling a member against a volume is the
	## kind of test that passes in the lab and fails in the render, because
	## the case that matters - a long brace grazing the rim of a bowl - is
	## exactly the case a coarse sample walks straight past.
	##
	## Clip the segment to the volume's height band first, then the question
	## is a two-dimensional one: how close does the surviving piece come to
	## the axis.
	var bottom := float(volume["bottom"])
	var top := float(volume["top"])
	var low := 0.0
	var high := 1.0
	var rise := to.y - from.y
	if absf(rise) < 1.0e-9:
		if from.y < bottom or from.y > top:
			return true
	else:
		var at_bottom := (bottom - from.y) / rise
		var at_top := (top - from.y) / rise
		low = maxf(0.0, minf(at_bottom, at_top))
		high = minf(1.0, maxf(at_bottom, at_top))
		if low > high:
			return true

	var flat_from := Vector2(from.x, from.z)
	var flat_to := Vector2(to.x, to.z)
	var head := flat_from.lerp(flat_to, low)
	var tail := flat_from.lerp(flat_to, high)
	var axis := Vector2(float(volume["x"]), float(volume["z"]))
	var span := tail - head
	var nearest := 0.0
	if span.length_squared() > 1.0e-12:
		nearest = clampf((axis - head).dot(span) / span.length_squared(), 0.0, 1.0)
	return head.lerp(tail, nearest).distance_to(axis) >= float(volume["radius"])


static func point_clears_all(point: Vector3, volumes: Array) -> bool:
	for volume in volumes:
		if not point_clears(point, volume):
			return false
	return true


static func segment_clears_all(from: Vector3, to: Vector3,
		volumes: Array) -> bool:
	for volume in volumes:
		if not segment_clears(from, to, volume):
			return false
	return true


static func ceiling_above(point: Vector3, volumes: Array) -> float:
	## The highest protected top the point sits inside the footprint of.
	##
	## What a bracket asks before it decides how far to drop: a leg that would
	## end inside a bowl can often be shortened until it ends above one, and a
	## short honest bracket beats a deleted one.
	var ceiling := -INF
	for volume in volumes:
		var dx := point.x - float(volume["x"])
		var dz := point.z - float(volume["z"])
		var radius := float(volume["radius"])
		if dx * dx + dz * dz < radius * radius:
			ceiling = maxf(ceiling, float(volume["top"]))
	return ceiling


static func longest_clear_run(path: Array, from_drop: float, to_drop: float,
		volumes: Array) -> Array:
	## The longest stretch of a track whose understructure clears every volume.
	##
	## A chute that ends over a bowl cannot carry its dark keel all the way to
	## the lip - the keel hangs half a unit below the running line and that is
	## exactly the half unit the bowl's mouth occupies. Trimming the spine and
	## cantilevering the last stretch is both what the picture needs and what
	## a moulded part would actually do.
	if volumes.is_empty() or path.size() < 2:
		return path.duplicate()

	var best_start := 0
	var best_length := 0
	var run_start := -1
	for index in path.size():
		var point: Vector3 = path[index]
		var clear := segment_clears_all(
			point - Vector3(0.0, from_drop, 0.0),
			point - Vector3(0.0, to_drop, 0.0), volumes)
		if clear:
			if run_start < 0:
				run_start = index
			if index - run_start + 1 > best_length:
				best_length = index - run_start + 1
				best_start = run_start
		else:
			run_start = -1

	if best_length < 4:
		return []
	return path.slice(best_start, best_start + best_length)


# --- structure ------------------------------------------------------------

static func column(height: float, half_width: float, fillet: float) -> ArrayMesh:
	## A structural column: a rounded box stood on end.
	##
	## Rounded rather than square because the reference's supports catch a
	## vertical highlight band down every one of them, and a square post
	## catches a one-pixel line instead. The band is what says "moulded".
	return Geometry.rounded_box(
		Vector3(half_width * 2.0, height, half_width * 2.0), fillet, 4)


static func collar(radius: float, thickness: float) -> ArrayMesh:
	## The band that wraps a column where a brace meets it.
	##
	## A joint that is merely two parts intersecting reads as a mistake; a
	## joint with a collar over it reads as a fitting. This is the cheapest
	## detail in the whole system and the one that does the most work.
	return Geometry.rounded_disc(radius, thickness, thickness * 0.45, 20, 3)


static func brace(from: Vector3, to: Vector3, radius: float,
		sides := 8) -> ArrayMesh:
	## Round stock between two points, in the parent's own space.
	return Geometry.tube([from, to], radius, sides)


static func hoop(radius: float, stock: float, segments := 40,
		sides := 8) -> ArrayMesh:
	## A closed horizontal ring of round stock: belts, guard rails, rim bands.
	var path: Array = []
	for step in segments + 1:
		var angle := TAU * float(step) / float(segments)
		path.append(Vector3(cos(angle) * radius, 0.0, sin(angle) * radius))
	return Geometry.tube(path, stock, sides)


static func arc_hoop(radius: float, stock: float, from_angle: float,
		to_angle: float, segments := 24, sides := 8) -> ArrayMesh:
	## An open arc of round stock: a partial guard, a grab rail, a cradle arm.
	var path: Array = []
	for step in segments + 1:
		var angle := lerpf(from_angle, to_angle, float(step) / float(segments))
		path.append(Vector3(cos(angle) * radius, 0.0, sin(angle) * radius))
	return Geometry.tube(path, stock, sides)


static func plate(size: Vector3, fillet: float) -> ArrayMesh:
	## A deck plate, cover panel or fascia: a flat filleted slab.
	return Geometry.rounded_box(size, fillet, 3)


# --- signage --------------------------------------------------------------
#
# A stroke alphabet, because a sign that does not say anything is a lit
# rectangle and a lit rectangle is what the start platform had. There is no
# text in this project's render path - no font, no label, no viewport that
# could bake one - so a legend has to be built out of the same solids as
# everything else, and at hero distance that is not a compromise: extruded
# letters standing proud of a recessed face catch the key on their top edges
# and read as a moulded sign, which a texture would not.
#
# Each glyph is a list of strokes in a unit box, given as centre, size and
# roll: `[cx, cy, w, h, degrees]`. Only the characters this machine needs
# exist. Adding one is four numbers a stroke, and an unknown character builds
# nothing rather than failing a render.

const GLYPH_STROKES := {
	"S": [
		[0.50, 0.92, 1.00, 0.16, 0.0],
		[0.08, 0.71, 0.16, 0.42, 0.0],
		[0.50, 0.50, 1.00, 0.16, 0.0],
		[0.92, 0.29, 0.16, 0.42, 0.0],
		[0.50, 0.08, 1.00, 0.16, 0.0],
	],
	"T": [
		[0.50, 0.92, 1.00, 0.16, 0.0],
		[0.50, 0.42, 0.18, 0.84, 0.0],
	],
	"A": [
		[0.50, 0.92, 0.84, 0.16, 0.0],
		[0.06, 0.42, 0.18, 0.84, 0.0],
		[0.94, 0.42, 0.18, 0.84, 0.0],
		[0.50, 0.44, 0.76, 0.15, 0.0],
	],
	"R": [
		[0.06, 0.50, 0.18, 1.00, 0.0],
		[0.52, 0.92, 0.76, 0.16, 0.0],
		[0.94, 0.72, 0.18, 0.42, 0.0],
		[0.48, 0.53, 0.68, 0.15, 0.0],
		[0.66, 0.24, 0.18, 0.56, 28.0],
	],
	"E": [
		[0.06, 0.50, 0.18, 1.00, 0.0],
		[0.54, 0.92, 0.80, 0.16, 0.0],
		[0.50, 0.50, 0.70, 0.15, 0.0],
		[0.54, 0.08, 0.80, 0.16, 0.0],
	],
	"D": [
		[0.06, 0.50, 0.18, 1.00, 0.0],
		[0.50, 0.92, 0.74, 0.16, 0.0],
		[0.50, 0.08, 0.74, 0.16, 0.0],
		[0.90, 0.50, 0.18, 0.72, 0.0],
	],
	"Y": [
		[0.24, 0.74, 0.17, 0.50, 22.0],
		[0.76, 0.74, 0.17, 0.50, -22.0],
		[0.50, 0.24, 0.18, 0.48, 0.0],
	],
	"-": [
		[0.50, 0.50, 0.80, 0.15, 0.0],
	],
}


static func legend(parent: Node3D, material: Material, text: String,
		width: float, height: float, depth: float, spacing := 0.30) -> void:
	## Extruded lettering centred on its parent's origin, facing +Z.
	##
	## `width` is the whole word's span and `height` one letter's cap height,
	## so a caller sizes the legend to the sign it has rather than to a point
	## size that would mean nothing here. The strokes are rounded boxes for
	## the same reason every other edge in this machine is: a square letter
	## catches a one-pixel highlight and a filleted one catches a band.
	var letters := text.to_upper()
	if letters.is_empty() or width <= 0.0:
		return
	var count := letters.length()
	var pitch := width / (float(count) + spacing * float(count - 1))
	var advance := pitch * (1.0 + spacing)
	var left := -width * 0.5 + pitch * 0.5

	for index in count:
		var glyph := letters[index]
		if not GLYPH_STROKES.has(glyph):
			continue
		var origin := Vector3(left + advance * float(index), 0.0, 0.0)
		var strokes: Array = GLYPH_STROKES[glyph]
		for stroke_index in strokes.size():
			var stroke: Array = strokes[stroke_index]
			var size := Vector3(float(stroke[2]) * pitch,
				float(stroke[3]) * height, depth)
			var bar := mesh_node(
				Geometry.rounded_box(size, minf(size.x, size.y) * 0.28, 2),
				material, "Glyph%d_%d" % [index, stroke_index], false)
			bar.position = origin + Vector3(
				(float(stroke[0]) - 0.5) * pitch,
				(float(stroke[1]) - 0.5) * height, 0.0)
			bar.rotation.z = deg_to_rad(float(stroke[4]))
			parent.add_child(bar)


# --- spline track ---------------------------------------------------------

static func smooth_path(controls: Array, samples: int) -> Array:
	## A Catmull-Rom spline through every control point.
	##
	## Authored track is a spline and not an arc chain, because the brief's
	## requirement is a *flowing* shape and an arc chain has a curvature
	## discontinuity at every joint. Those show up as a visible kink in the
	## highlight running down a glossy channel - the single clearest tell
	## that a track was generated rather than moulded.
	##
	## The end points are duplicated so the curve starts and ends exactly at
	## the first and last control, which is what lets a module hand its exit
	## point to the next module as an attachment.
	if controls.size() < 2:
		return controls.duplicate()
	var padded: Array = [controls[0]]
	padded.append_array(controls)
	padded.append(controls[controls.size() - 1])

	var path: Array = []
	var spans := padded.size() - 3
	for span in spans:
		var p0: Vector3 = padded[span]
		var p1: Vector3 = padded[span + 1]
		var p2: Vector3 = padded[span + 2]
		var p3: Vector3 = padded[span + 3]
		var last := samples if span == spans - 1 else samples - 1
		for step in last + 1:
			var t := float(step) / float(samples)
			path.append(_catmull_rom(p0, p1, p2, p3, t))
	return path


static func _catmull_rom(p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3,
		t: float) -> Vector3:
	var t2 := t * t
	var t3 := t2 * t
	return 0.5 * (
		2.0 * p1
		+ (p2 - p0) * t
		+ (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
		+ (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3)


static func offset_path(path: Array, lateral: float, vertical: float) -> Array:
	## The same path, shifted sideways and up in each sample's own frame.
	##
	## How a guard rail, an underside keel or an edge light follows a track
	## exactly. The frame is the path's horizontal direction with world up -
	## the same rule `toy_geometry.sweep` uses, so an offset path and the
	## sweep it decorates never drift apart.
	var out: Array = []
	for index in path.size():
		var before: Vector3 = path[maxi(index - 1, 0)]
		var after: Vector3 = path[mini(index + 1, path.size() - 1)]
		var forward := Vector3(after.x - before.x, 0.0, after.z - before.z)
		if forward.length_squared() < 1.0e-12:
			forward = Vector3(0.0, 0.0, 1.0)
		forward = forward.normalized()
		var side := Vector3(forward.z, 0.0, -forward.x)
		out.append(path[index] + side * lateral + Vector3.UP * vertical)
	return out


static func sample_at(path: Array, t: float) -> Vector3:
	## A point a fraction of the way along a sampled path, by index.
	if path.is_empty():
		return Vector3.ZERO
	var at: float = clampf(t, 0.0, 1.0) * float(path.size() - 1)
	var low := int(floor(at))
	var high: int = mini(low + 1, path.size() - 1)
	return (path[low] as Vector3).lerp(path[high], at - float(low))


# --- mechanism ------------------------------------------------------------

static func paddle(length: float, width: float, thickness: float,
		fillet: float) -> ArrayMesh:
	## One broad rounded blade of a collector hub, lying along +X.
	return Geometry.rounded_box(
		Vector3(length, thickness, width), fillet, 4)


static func hub_housing(radius: float, height: float) -> ArrayMesh:
	## The stepped drum a rotating mechanism sits in.
	##
	## Three diameters rather than one: a wide base flange, a waist, and a
	## capped crown. A single cylinder is a shape; a stepped drum is a part.
	var points: Array = [
		Vector2(0.0, -height * 0.5),
		Vector2(radius, -height * 0.5),
		Vector2(radius, -height * 0.5),
		Vector2(radius, -height * 0.18),
		Vector2(radius * 0.74, -height * 0.06),
		Vector2(radius * 0.74, -height * 0.06),
		Vector2(radius * 0.74, height * 0.24),
		Vector2(radius * 0.90, height * 0.34),
		Vector2(radius * 0.90, height * 0.34),
		Vector2(radius * 0.90, height * 0.44),
		Vector2(radius * 0.62, height * 0.5),
		Vector2(0.0, height * 0.5),
	]
	return Geometry.lathe(points, Geometry.profile_normals(points), 40)


static func bowl_profile(inner_radius: float, depth: float, drain_radius: float,
		rounds := 10) -> Array:
	## The running surface of a bowl, as a lathe profile.
	##
	## A cosine dish rather than a cone or a hemisphere. A cone lights as a
	## flat facet and a hemisphere is too steep at the rim to keep a marble
	## visible - the dish holds a shallow lit shoulder where the field runs
	## and steepens only near the drain, which is the shape the concept's
	## mixing bowl actually has.
	var points: Array = [Vector2(drain_radius, -depth)]
	for step in range(1, rounds + 1):
		var t := float(step) / float(rounds)
		var radius: float = lerpf(drain_radius, inner_radius, t)
		var height: float = -depth * (0.5 + 0.5 * cos(t * PI))
		points.append(Vector2(radius, height))
	return points


static func bolt_ring(parent: Node3D, material: Material, count: int,
		radius: float, height: float, bolt_radius: float,
		bolt_height: float) -> void:
	## Small hardware evenly around a circle, added straight to `parent`.
	##
	## The small-scale layer, and deliberately the thinnest of the three: the
	## brief's warning about greebles is that they read as noise at any
	## distance where the module itself is legible. A ring of bolts survives
	## because it is *regular* - the eye resolves it as one band of texture
	## rather than as many objects.
	var mesh := Geometry.rounded_disc(bolt_radius, bolt_height,
		bolt_height * 0.45, 10, 2)
	for index in count:
		var angle := TAU * float(index) / float(maxi(count, 1))
		var node := mesh_node(mesh, material, "Bolt%d" % index, false)
		node.position = Vector3(cos(angle) * radius, height, sin(angle) * radius)
		parent.add_child(node)


static func equipment_rack(parent: Node3D, shell: Material, warm: Material,
		lit: Material, seed_index: int, span: float) -> void:
	## A cluster of small housings on a deck edge: the machinery read.
	##
	## Six boxes at three heights with a warm cap and one lit face each. The
	## layout is arithmetic on `seed_index`, not random, so a rack placed at
	## two levels differs between them without either being unrepeatable.
	var count := 6
	for index in count:
		var t := float(index) / float(count - 1)
		var wobble := float((seed_index * 7 + index * 3) % 5) / 5.0
		var box_height: float = 0.20 + wobble * 0.26
		var box := mesh_node(
			Geometry.rounded_box(
				Vector3(0.20 + wobble * 0.10, box_height, 0.17), 0.045, 3),
			shell, "Unit%d" % index)
		box.position = Vector3(
			lerpf(-span * 0.5, span * 0.5, t), box_height * 0.5, 0.0)
		parent.add_child(box)

		var cap := mesh_node(
			Geometry.rounded_box(
				Vector3(0.23 + wobble * 0.10, 0.05, 0.19), 0.02, 2),
			warm, "UnitCap%d" % index, false)
		cap.position = box.position + Vector3(0.0, box_height * 0.5 + 0.02, 0.0)
		parent.add_child(cap)

		if index % 2 == 0:
			var lamp := mesh_node(
				Geometry.rounded_box(Vector3(0.05, 0.05, 0.02), 0.012, 2),
				lit, "UnitLamp%d" % index, false)
			lamp.position = box.position + Vector3(0.0, 0.02, 0.10)
			parent.add_child(lamp)
