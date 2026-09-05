extends RefCounted

## What stands behind the machine, and how little of it there is.
##
## The reference is not shot against black. It is shot against a dark cliff
## with a haze on it and a scatter of distant lights, and that matters for a
## reason that is optical rather than decorative: a black surround gives a
## glossy subject nothing to reflect, so every clearcoat highlight collapses
## to the direct lights alone and the machine reads as flat. A backdrop two or
## three stops under the subject returns a faint sheen along every rounded
## edge, and that sheen is most of the "photographed" quality.
##
## The rule the brief sets is that the subject stays dominant, so this file is
## deliberately impoverished:
##
## * three depth layers, no more
## * every surface flat-shaded, rough, unlit by any practical
## * no silhouette allowed to cross the machine's own outline near the centre
## * lights are single emissive chips, placed by arithmetic, never bright
##   enough to compete with a marble
##
## Nothing here casts or receives a shadow. It is a painted flat with parallax,
## and it costs about nine hundred triangles.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "Backdrop"

	_ridge(root, palette)
	_towers(root, palette)
	_gantries(root, palette)

	return root


static func _ridge(root: Node3D, palette) -> void:
	## The far crag. Eight blocks, tilted and part-buried, reading as rock at
	## the distance and exposure they are seen at.
	var mesh := Geometry.rounded_box(Vector3(26.0, 30.0, 12.0), 0.9, 2)
	for index in 8:
		var step := float(index) - 3.5
		var node := Forms.mesh_node(mesh, palette.get_material("backdrop_far"),
			"Crag%d" % index, false)
		node.position = Vector3(step * 19.0, -4.0 - absf(step) * 2.2, -84.0
			+ float((index * 5) % 4) * 8.0)
		node.rotation = Vector3(0.0, step * 0.16, 0.10 * (1.0 if index % 2 == 0 else -1.0))
		node.scale = Vector3(1.0, 0.7 + float((index * 3) % 5) * 0.20, 1.0)
		root.add_child(node)


static func _towers(root: Node3D, palette) -> void:
	## Mid-distance structures, cleared of the centre of frame.
	##
	## The gap either side of the machine is the composition: the concept puts
	## its tower in a slot of empty air and its scenery outboard of that, so
	## the subject's silhouette is never confused with the background's.
	var slab := Geometry.rounded_box(Vector3(5.6, 34.0, 5.6), 0.22, 2)
	var caps := Geometry.rounded_box(Vector3(6.6, 0.9, 6.6), 0.12, 2)
	var offsets := [-19.0, -12.5, 12.5, 19.5, -26.0, 27.0]
	for index in offsets.size():
		var x: float = offsets[index]
		var depth: float = -37.0 - float((index * 7) % 5) * 6.5
		var height_scale: float = 0.62 + float((index * 3) % 6) * 0.13

		var body := Forms.mesh_node(slab, palette.get_material("backdrop_mid"),
			"Tower%d" % index, false)
		body.position = Vector3(x, 34.0 * height_scale * 0.5 - 9.0, depth)
		body.scale = Vector3(1.0, height_scale, 1.0)
		body.rotation.y = float(index) * 0.29
		root.add_child(body)

		var cap := Forms.mesh_node(caps, palette.get_material("backdrop_near"),
			"TowerCap%d" % index, false)
		cap.position = Vector3(x, 34.0 * height_scale - 9.0, depth)
		cap.rotation.y = body.rotation.y
		root.add_child(cap)

		_windows(root, palette, body.position, height_scale, index)


static func _windows(root: Node3D, palette, centre: Vector3,
		height_scale: float, seed_index: int) -> void:
	## A handful of lit chips per tower. Warm, dim, and never in a grid - a
	## regular grid at this exposure reads as a texture error.
	var chip := Geometry.rounded_box(Vector3(0.55, 0.28, 0.10), 0.04, 2)
	var count := 5
	for index in count:
		if (seed_index * 5 + index * 3) % 4 == 0:
			continue
		var t := (float(index) + 0.5) / float(count)
		var node := Forms.mesh_node(chip, palette.get_material("lit_window"),
			"Window%d_%d" % [seed_index, index], false)
		node.position = centre + Vector3(
			-2.0 + float((seed_index + index * 2) % 4) * 1.3,
			(t - 0.5) * 34.0 * height_scale * 0.8,
			2.9)
		root.add_child(node)


static func _gantries(root: Node3D, palette) -> void:
	## Two dark lattice masts close in, one each side, well outboard of the
	## machine. They are the only backdrop element with visible structure, and
	## they exist to give the mid-ground a scale reference.
	for side in 2:
		var x: float = 11.5 * (1.0 if side == 0 else -1.0)
		var mast := Node3D.new()
		mast.name = "Gantry%d" % side
		mast.position = Vector3(x, 0.0, -18.0)
		root.add_child(mast)

		for leg in 2:
			var leg_x: float = 1.1 * (1.0 if leg == 0 else -1.0)
			var post := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.55, 27.0, 0.55), 0.15, 3),
				palette.get_material("backdrop_near"), "Post%d" % leg, false)
			post.position = Vector3(leg_x, 9.5, 0.0)
			mast.add_child(post)

		for rung in 9:
			var y := 0.5 + float(rung) * 2.7
			var bar := Forms.mesh_node(
				Geometry.rounded_box(Vector3(2.7, 0.30, 0.30), 0.10, 2),
				palette.get_material("backdrop_near"), "Rung%d" % rung, false)
			bar.position = Vector3(0.0, y, 0.0)
			mast.add_child(bar)

		var beacon := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.35, 0.35, 0.35), 0.12, 2),
			palette.get_material("lit_cyan_soft"), "Beacon", false)
		beacon.position = Vector3(0.0, 23.4, 0.0)
		mast.add_child(beacon)
