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
	return offset_path_framed(
		path, Geometry.world_ups(path.size()), lateral, vertical)


static func offset_path_framed(path: Array, ups: Array, lateral: float,
		vertical: float) -> Array:
	## `offset_path`, banked: the offset is taken in the supplied frame.
	##
	## The reason this exists is that "never drift apart" above is only true
	## while the sweep and the offset agree about which way is up. On the
	## simulated curve they do not: the channel is swept along frames rolled
	## 27.7 degrees into the turn, and the same offsets taken against world up
	## put the lip, the fascia, the keel, the underlight and the guards
	## somewhere else entirely - the acrylic guard by more than a marble
	## diameter, which is enough to leave it standing clear of the wall it is
	## meant to be mounted on. Banked track therefore takes its offsets in the
	## frame it was swept in, and the five stacked layers stay stacked.
	var out: Array = []
	for index in path.size():
		var side := Geometry.lateral_frame(path, ups, index)
		out.append(path[index] + side * lateral + (ups[index] as Vector3) * vertical)
	return out


static func sample_at(path: Array, t: float) -> Vector3:
	## A point a fraction of the way along a sampled path, by index.
	if path.is_empty():
		return Vector3.ZERO
	var at: float = clampf(t, 0.0, 1.0) * float(path.size() - 1)
	var low := int(floor(at))
	var high: int = mini(low + 1, path.size() - 1)
	return (path[low] as Vector3).lerp(path[high], at - float(low))


static func sample_basis(path: Array, ups: Array, t: float) -> Basis:
	## The track's own axes a fraction of the way along it.
	##
	## `sample_at` answers where a bracket goes; this answers which way it
	## faces. On level track the two are separable and nobody notices, because
	## a part bolted to a flat channel is upright whatever the channel does in
	## plan. On a 27.7 degree bank they are not: an upright post on a tilted
	## channel is a part that missed its mounting face, and it reads as one
	## from any angle that shows the track's section.
	##
	## Columns are lateral, up, flow - the same frame `sweep_framed` carries
	## its cross-section in, so a part placed by this and a surface swept along
	## that agree about where the track's own X and Y are.
	if path.is_empty():
		return Basis.IDENTITY
	var at: float = clampf(t, 0.0, 1.0) * float(path.size() - 1)
	var index := mini(int(floor(at)), path.size() - 1)
	var side := Geometry.lateral_frame(path, ups, index)
	var up: Vector3 = (ups[index] as Vector3).normalized()
	return Basis(side, up, side.cross(up))


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
