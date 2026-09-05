extends RefCounted

## The dark structure the whole machine hangs on.
##
## This module is the diagnosis of every previous prototype, built as a part.
## V0.3, V0.4, the neon proofs and the toy style-lock all rendered *track* and
## nothing else: a bright object floating in air with a black surround. The
## reference concept is not built that way. Measure its hero column and about
## two thirds of the lit area is dark scaffolding - masts, belts, braces, deck
## plates, equipment - and only a third is the running surface. The scaffolding
## is what gives the tower a silhouette, what makes the track read as *mounted*
## rather than drawn, and what fills the space between modules so that pulling
## the camera back reveals design instead of emptiness.
##
## So the structure is authored first and the modules are attached to it.
##
## ## Why the frame stands behind and not around
##
## The obvious layout - four columns on a rectangle with the modules stacked
## inside - cannot be built. The bowl is 6.7 units across its guard and the
## collector 5.9, so any column close enough to look like a tower passes
## straight through a running surface. Every arrangement that avoids that ends
## up in the same place: a triangular frame standing *behind* the run, with
## brackets reaching forward to take each module, and short post clusters
## filling the gaps between modules where nothing else is in the way.
##
## That is also what the reference actually has. Its alternative-angle panel
## shows the lattice behind the track and never inside it.
##
## ## The three variants change this module most
##
## `tower` - three slim masts, a belt at every level, an X in every bay, post
## clusters in both gaps. Dense, vertical, closest to the reference.
##
## `deck` - heavier masts carrying solid back-plates instead of diagonals, and
## a wide plinth. Reads as a stacked appliance: calmer, more horizontal.
##
## `spine` - one very heavy back mast with cantilever yokes and two thin
## outriggers. The most open silhouette, and the one with the most visible
## warm hardware, because a cantilever needs a joint.
##
## The rest of the machine does not know which it got.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")

# The three feet, well outboard of every module radius. The bowl's acrylic
# guard reaches 3.36 and the collector 2.95; the nearest mast is 4.47 from the
# machine's axis, which leaves a clear unit of air at the widest point.
const MAST_RIGHT := Vector3(3.85, 0.0, -0.70)
const MAST_LEFT := Vector3(-3.85, 0.0, -0.70)
const MAST_BACK := Vector3(0.0, 0.0, -3.90)

# The two vertical gaps between modules, where a post cluster can stand
# without touching a running surface. Kept here rather than in the scene
# because they are a property of *this* frame's clearances.
const GAP_LOWER := Vector2(3.30, 9.80)
const GAP_UPPER := Vector2(12.85, 14.60)


static func build(palette, levels: Array, top: float) -> Node3D:
	var root := Node3D.new()
	root.name = "SupportTower"
	_base(root, palette)
	match palette.variant:
		"deck":
			_build_deck(root, palette, levels, top)
		"spine":
			_build_spine(root, palette, levels, top)
		_:
			_build_tower(root, palette, levels, top)
	return root


# --- shared parts ---------------------------------------------------------

static func _column(root: Node3D, palette, at: Vector3, from_y: float,
		to_y: float, half_width: float, node_name: String) -> void:
	var height := to_y - from_y
	var post := Forms.mesh_node(
		Geometry.rounded_box(Vector3(half_width * 2.0, height, half_width * 2.0),
			half_width * 0.42, 4),
		palette.get_material("graphite"), node_name)
	post.position = Vector3(at.x, from_y + height * 0.5, at.z)
	root.add_child(post)

	# The face strip: one lighter plane down the front of the post. A column
	# with a single albedo is a bar; a column with a recessed lighter face is
	# an extrusion, and the difference costs one box.
	var face := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(half_width * 1.05, height - 0.4, half_width * 0.24), 0.03, 2),
		palette.get_material("graphite_soft"), node_name + "Face", false)
	face.position = Vector3(at.x, from_y + height * 0.5, at.z + half_width * 1.02)
	root.add_child(face)


static func _collars(root: Node3D, palette, at: Vector3, levels: Array,
		radius: float, node_name: String) -> void:
	## A gold fitting where every level crosses a mast.
	##
	## The same gold at every level: a repeated warm note running the height
	## of the machine is what stops the structure reading as one dark mass,
	## and it costs one disc per crossing.
	var mesh := Forms.collar(radius, 0.14)
	for index in levels.size():
		var node := Forms.mesh_node(mesh, palette.get_material("gold"),
			"%s%d" % [node_name, index], false)
		node.position = Vector3(at.x, float(levels[index]), at.z)
		root.add_child(node)


static func _belt(root: Node3D, palette, feet: Array, y: float, stock: float,
		suffix: String) -> void:
	## One horizontal band right round the frame, plus its warm trim.
	var path: Array = []
	for foot in feet:
		path.append(Vector3(foot.x, y, foot.z))
	path.append(Vector3(feet[0].x, y, feet[0].z))

	root.add_child(Forms.mesh_node(
		Geometry.tube(path, stock, 8),
		palette.get_material("graphite_soft"), "Belt" + suffix))

	var trim_path: Array = []
	for point in path:
		trim_path.append(point + Vector3(0.0, stock * 1.7, 0.0))
	root.add_child(Forms.mesh_node(
		Geometry.tube(trim_path, stock * 0.34, 6),
		palette.get_material("gold"), "BeltTrim" + suffix, false))


static func _light_strip(root: Node3D, palette, at: Vector3, from_y: float,
		to_y: float, key: String, node_name: String) -> void:
	var height := to_y - from_y
	var strip := Forms.mesh_node(
		Geometry.rounded_box(Vector3(0.085, height, 0.035), 0.016, 2),
		palette.get_material(key), node_name, false)
	strip.position = Vector3(at.x, from_y + height * 0.5, at.z)
	root.add_child(strip)


static func _service_deck(root: Node3D, palette, at: Vector3, span: float,
		seed_index: int, yaw := 0.0) -> void:
	## A small platform with a rack of housings on it.
	##
	## The reference scatters these all down its tower and they are most of
	## what makes it look inhabited by machinery. Four or five per frame is
	## enough; more and the silhouette starts to blur.
	var deck := Node3D.new()
	deck.name = "ServiceDeck%d" % seed_index
	deck.position = at
	deck.rotation.y = yaw
	root.add_child(deck)

	deck.add_child(Forms.mesh_node(
		Forms.plate(Vector3(span, 0.11, 0.56), 0.04),
		palette.get_material("graphite_soft"), "Plate"))

	var lip := Forms.mesh_node(
		Forms.plate(Vector3(span, 0.05, 0.07), 0.02),
		palette.get_material("silver_deep"), "Lip", false)
	lip.position = Vector3(0.0, 0.055, 0.28)
	deck.add_child(lip)

	var rack := Node3D.new()
	rack.name = "Rack"
	rack.position = Vector3(0.0, 0.055, 0.0)
	deck.add_child(rack)
	Forms.equipment_rack(rack, palette.get_material("graphite"),
		palette.get_material("gold"), palette.get_material("lit_cyan_soft"),
		seed_index, span * 0.76)


static func _post_cluster(root: Node3D, palette, gap: Vector2, half_x: float,
		z: float, half_width: float, suffix: String) -> void:
	## Four short posts filling a gap between modules, banded top and bottom.
	##
	## These are what stop the machine reading as modules floating one above
	## another. They stand only where the gap allows, which is why the frame
	## keeps its clearances in constants rather than in the scene.
	var feet := [
		Vector3(half_x, 0.0, z + 0.55), Vector3(-half_x, 0.0, z + 0.55),
		Vector3(-half_x, 0.0, z - 0.55), Vector3(half_x, 0.0, z - 0.55),
	]
	for index in feet.size():
		_column(root, palette, feet[index], gap.x, gap.y, half_width,
			"Cluster%s_%d" % [suffix, index])

	for edge in [gap.x + 0.25, (gap.x + gap.y) * 0.5, gap.y - 0.25]:
		_belt(root, palette, feet, edge, 0.06, "%s_%d" % [suffix, int(edge * 10)])

	# One X across the back of the cluster only: the front stays open because
	# the camera looks through it at the track.
	for cross in 2:
		var a: Vector3 = feet[2] if cross == 0 else feet[3]
		var b: Vector3 = feet[3] if cross == 0 else feet[2]
		root.add_child(Forms.mesh_node(
			Forms.brace(a + Vector3(0.0, gap.x + 0.25, 0.0),
				b + Vector3(0.0, gap.y - 0.25, 0.0), 0.045, 6),
			palette.get_material("graphite_soft"), "ClusterX%s_%d" % [suffix, cross]))

	_light_strip(root, palette, Vector3(half_x, 0.0, z + 0.55 + half_width),
		gap.x + 0.4, gap.y - 0.4, "lit_cyan_soft", "ClusterStrip" + suffix)


static func _yoke(root: Node3D, palette, y: float, reach: float,
		suffix: String) -> void:
	## Two brackets reaching in from the side masts to take a module, plus a
	## rear tie to the back mast. Three-point support, visibly.
	for side in 2:
		var mast: Vector3 = MAST_RIGHT if side == 0 else MAST_LEFT
		var inner := Vector3(reach * (1.0 if side == 0 else -1.0), y, -0.35)
		root.add_child(Forms.mesh_node(
			Forms.brace(Vector3(mast.x, y, mast.z), inner, 0.11, 8),
			palette.get_material("graphite"), "Yoke%s_%d" % [suffix, side]))

		var pad := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.46, 0.16, 0.34), 0.06, 3),
			palette.get_material("gold"), "YokePad%s_%d" % [suffix, side], false)
		pad.position = inner + Vector3(0.0, 0.10, 0.0)
		root.add_child(pad)

		root.add_child(Forms.mesh_node(
			Forms.brace(Vector3(mast.x, y + 1.35, mast.z),
				inner + Vector3(0.0, 0.10, 0.0), 0.045, 6),
			palette.get_material("chrome"), "YokeTie%s_%d" % [suffix, side]))

	root.add_child(Forms.mesh_node(
		Forms.brace(Vector3(MAST_BACK.x, y, MAST_BACK.z),
			Vector3(0.0, y, -0.9), 0.10, 8),
		palette.get_material("graphite"), "YokeRear" + suffix))


static func _base(root: Node3D, palette) -> void:
	## The plinth. Every playset stands on one, and it is where the machine
	## stops being a tower and becomes a product on a shelf.
	var radius := 3.95
	var pad := Forms.mesh_node(
		Geometry.rounded_disc(radius, 0.58, 0.17, 56, 4),
		palette.get_material("graphite_deep"), "BasePad")
	pad.position = Vector3(0.0, 0.29, 0.0)
	root.add_child(pad)

	var step := Forms.mesh_node(
		Geometry.rounded_disc(radius * 0.84, 0.34, 0.11, 56, 4),
		palette.get_material("graphite"), "BaseStep")
	step.position = Vector3(0.0, 0.72, 0.0)
	root.add_child(step)

	var band := Forms.mesh_node(
		Forms.hoop(radius * 0.885, 0.06, 64, 8),
		palette.get_material("gold"), "BaseBand", false)
	band.position = Vector3(0.0, 0.62, 0.0)
	root.add_child(band)

	var glow := Forms.mesh_node(
		Forms.hoop(radius * 0.97, 0.038, 64, 6),
		palette.get_material("lit_gold"), "BaseGlow", false)
	glow.position = Vector3(0.0, 0.50, 0.0)
	root.add_child(glow)

	Forms.bolt_ring(root, palette.get_material("chrome"), 16, radius * 0.70,
		0.90, 0.075, 0.055)


static func _ring_deck(root: Node3D, palette, y: float, radius: float,
		seed_index: int, accent := "neon_cyan") -> void:
	## A curved walkway wrapping the back of the machine at one height.
	##
	## The single largest thing missing from the first hero frame. The
	## reference tower reads as many stacked levels because it *has* many:
	## every module sits on a visible circular deck with a rail round it and
	## equipment on it, and the decks continue between the modules where no
	## module is. Without them a four-module machine is four objects with air
	## in between, which is what the first pass rendered.
	##
	## It spans 190 to 350 degrees - the back - because that is the arc no
	## chute occupies. A full ring would cut through the track, and a deck the
	## camera saw through the front of would hide the modules it exists to
	## frame.
	var from_angle := deg_to_rad(190.0)
	var to_angle := deg_to_rad(350.0)
	var inner := radius - 0.62

	var deck := Node3D.new()
	deck.name = "RingDeck%d" % seed_index
	deck.position = Vector3(0.0, y, 0.0)
	root.add_child(deck)

	var plate: Array = [
		Vector2(inner, 0.0), Vector2(radius, 0.0),
		Vector2(radius, -0.13), Vector2(inner, -0.13), Vector2(inner, 0.0),
	]
	deck.add_child(Forms.mesh_node(
		Geometry.lathe(plate, Geometry.profile_normals(plate, true), 40,
			from_angle, to_angle),
		palette.get_material("graphite_soft"), "Plate"))

	var fascia: Array = [
		Vector2(radius, -0.13), Vector2(radius + 0.04, -0.20),
		Vector2(radius + 0.04, -0.27), Vector2(radius - 0.02, -0.31),
	]
	deck.add_child(Forms.mesh_node(
		Geometry.lathe(fascia, Geometry.profile_normals(fascia, true), 40,
			from_angle, to_angle),
		palette.get_material("gold"), "Fascia"))

	var glow := Forms.mesh_node(
		Forms.arc_hoop(radius + 0.03, 0.028, from_angle, to_angle, 40, 6),
		palette.get_material(accent), "Glow", false)
	glow.position = Vector3(0.0, -0.35, 0.0)
	deck.add_child(glow)

	# The rail: two arcs of round stock on short stanchions. A deck without a
	# rail is a shelf, and the rail is what makes it somewhere a person could
	# stand - scale in a toy comes from implied human scale.
	for level in 2:
		var lift: float = 0.42 if level == 0 else 0.70
		var rail := Forms.mesh_node(
			Forms.arc_hoop(radius - 0.06, 0.032, from_angle, to_angle, 40, 6),
			palette.get_material("silver_deep"), "Rail%d" % level, false)
		rail.position = Vector3(0.0, lift, 0.0)
		deck.add_child(rail)

	var stanchion := Geometry.rounded_box(Vector3(0.06, 0.72, 0.06), 0.02, 2)
	for index in 9:
		var angle: float = lerpf(from_angle, to_angle, float(index) / 8.0)
		var post := Forms.mesh_node(stanchion, palette.get_material("graphite"),
			"Stanchion%d" % index, false)
		post.position = Vector3(cos(angle) * (radius - 0.06), 0.36,
			sin(angle) * (radius - 0.06))
		deck.add_child(post)

	var rack := Node3D.new()
	rack.name = "Rack"
	var rack_angle: float = lerpf(from_angle, to_angle,
		0.25 + 0.5 * float(seed_index % 2))
	rack.position = Vector3(cos(rack_angle) * (radius - 0.34), 0.0,
		sin(rack_angle) * (radius - 0.34))
	rack.rotation.y = -rack_angle
	deck.add_child(rack)
	Forms.equipment_rack(rack, palette.get_material("graphite"),
		palette.get_material("gold"), palette.get_material("lit_cyan_soft"),
		seed_index + 5, 1.5)


# --- variant: tower -------------------------------------------------------

static func _build_tower(root: Node3D, palette, levels: Array,
		top: float) -> void:
	var feet := [MAST_RIGHT, MAST_LEFT, MAST_BACK]

	for index in feet.size():
		_column(root, palette, feet[index], 0.85, top, 0.145, "Mast%d" % index)
		_collars(root, palette, feet[index], levels, 0.25, "Collar%d_" % index)

	var belts: Array = [1.30]
	belts.append_array(levels)
	belts.append(top - 0.30)

	# A cap on each mast. A column that simply stops reads as cropped; a
	# column with a finial reads as finished, and the frame needs to finish
	# just above the sign rather than carry on into empty sky.
	for index in feet.size():
		var cap := Forms.mesh_node(Forms.collar(0.26, 0.16),
			palette.get_material("gold"), "MastCap%d" % index, false)
		cap.position = Vector3(feet[index].x, top + 0.04, feet[index].z)
		root.add_child(cap)
		var pip := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.10, 0.20, 0.10), 0.04, 2),
			palette.get_material("lit_cyan"), "MastPip%d" % index, false)
		pip.position = Vector3(feet[index].x, top + 0.20, feet[index].z)
		root.add_child(pip)
	for index in belts.size():
		_belt(root, palette, feet, float(belts[index]), 0.062, str(index))

	var pairs := [[0, 2], [1, 2], [0, 1]]
	for bay in belts.size() - 1:
		var low := float(belts[bay])
		var high := float(belts[bay + 1])
		if high - low < 0.9:
			continue
		for pair_index in pairs.size():
			var pair: Array = pairs[pair_index]
			var a: Vector3 = feet[int(pair[0])]
			var b: Vector3 = feet[int(pair[1])]
			for cross in 2:
				root.add_child(Forms.mesh_node(
					Forms.brace(
						a + Vector3(0.0, low if cross == 0 else high, 0.0),
						b + Vector3(0.0, high if cross == 0 else low, 0.0),
						0.036, 6),
					palette.get_material("graphite_soft"),
					"Brace%d_%d_%d" % [bay, pair_index, cross]))

	_post_cluster(root, palette, GAP_LOWER, 1.15, -1.35, 0.17, "Low")
	_post_cluster(root, palette, GAP_UPPER, 1.15, -0.75, 0.15, "High")

	_yoke(root, palette, 10.95, 2.70, "Bowl")
	_yoke(root, palette, 14.60, 1.80, "Start")

	_light_strip(root, palette, MAST_RIGHT + Vector3(0.0, 0.0, 0.21), 1.4,
		top - 0.9, "lit_cyan_soft", "MastStripR")
	_light_strip(root, palette, MAST_LEFT + Vector3(0.0, 0.0, 0.21), 1.4,
		top - 0.9, "lit_cyan_soft", "MastStripL")

	_ring_deck(root, palette, 6.20, 3.30, 0, "neon_violet")
	_ring_deck(root, palette, 8.55, 3.30, 1, "neon_cyan")
	_ring_deck(root, palette, 13.95, 2.85, 2, "neon_cyan")

	_service_deck(root, palette, MAST_RIGHT + Vector3(-0.85, 6.55, 0.42),
		1.7, 0, -0.35)
	_service_deck(root, palette, MAST_LEFT + Vector3(0.85, 4.10, 0.42),
		1.7, 1, 0.35)
	_service_deck(root, palette, MAST_RIGHT + Vector3(-0.80, 13.25, 0.42),
		1.4, 2, -0.35)
	_service_deck(root, palette, MAST_LEFT + Vector3(0.80, 16.20, 0.42),
		1.4, 3, 0.35)


# --- variant: deck --------------------------------------------------------

static func _build_deck(root: Node3D, palette, levels: Array,
		top: float) -> void:
	## Heavier masts carrying solid back-plates. Calmer, more horizontal.
	var feet := [
		MAST_RIGHT + Vector3(0.45, 0.0, 0.0),
		MAST_LEFT + Vector3(-0.45, 0.0, 0.0),
		MAST_BACK + Vector3(0.0, 0.0, -0.4),
	]

	for index in feet.size():
		_column(root, palette, feet[index], 0.85, top, 0.30, "Mast%d" % index)
		_collars(root, palette, feet[index], levels, 0.44, "Collar%d_" % index)

	# A solid panel spanning the back of every bay, in place of diagonals.
	var edges: Array = [1.30]
	edges.append_array(levels)
	edges.append(top - 0.45)
	for index in edges.size() - 1:
		var low := float(edges[index])
		var high := float(edges[index + 1])
		if high - low < 1.1:
			continue
		var panel := Forms.mesh_node(
			Forms.plate(Vector3(8.6, high - low - 0.5, 0.26), 0.09),
			palette.get_material("graphite_soft"), "Panel%d" % index)
		panel.position = Vector3(0.0, (low + high) * 0.5, feet[0].z - 0.10)
		root.add_child(panel)

		var fascia := Forms.mesh_node(
			Forms.plate(Vector3(8.7, 0.14, 0.34), 0.05),
			palette.get_material("gold"), "PanelFascia%d" % index, false)
		fascia.position = Vector3(0.0, low + 0.34, feet[0].z - 0.10)
		root.add_child(fascia)

		var glow := Forms.mesh_node(
			Forms.plate(Vector3(8.2, 0.05, 0.10), 0.02),
			palette.get_material("lit_cyan_soft"), "PanelGlow%d" % index, false)
		glow.position = Vector3(0.0, low + 0.22, feet[0].z + 0.06)
		root.add_child(glow)

	for index in edges.size():
		_belt(root, palette, feet, float(edges[index]), 0.11, str(index))

	_post_cluster(root, palette, GAP_LOWER, 1.45, -1.35, 0.24, "Low")
	_post_cluster(root, palette, GAP_UPPER, 1.45, -0.75, 0.20, "High")

	_yoke(root, palette, 10.95, 2.90, "Bowl")
	_yoke(root, palette, 14.60, 2.00, "Start")

	_ring_deck(root, palette, 6.20, 3.55, 0, "neon_violet")
	_ring_deck(root, palette, 8.55, 3.55, 1, "neon_cyan")
	_ring_deck(root, palette, 13.95, 3.05, 2, "neon_cyan")

	_service_deck(root, palette, Vector3(-3.30, 5.10, -1.30), 2.1, 4)
	_service_deck(root, palette, Vector3(3.30, 12.10, -1.30), 2.1, 5)


# --- variant: spine -------------------------------------------------------

static func _build_spine(root: Node3D, palette, levels: Array,
		top: float) -> void:
	## One mast, two thin outriggers, a cantilever yoke per module.
	var mast := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.55, top - 0.85, 1.35), 0.30, 4),
		palette.get_material("graphite"), "Mast")
	mast.position = Vector3(0.0, (top + 0.85) * 0.5, -4.05)
	root.add_child(mast)

	var mast_face := Forms.mesh_node(
		Geometry.rounded_box(Vector3(0.95, top - 2.2, 0.14), 0.05, 3),
		palette.get_material("graphite_soft"), "MastFace", false)
	mast_face.position = Vector3(0.0, (top + 0.85) * 0.5, -3.34)
	root.add_child(mast_face)

	_light_strip(root, palette, Vector3(0.0, 0.0, -3.26), 1.5, top - 1.2,
		"lit_cyan_soft", "MastStrip")

	var outriggers := [Vector3(4.60, 0.0, -2.40), Vector3(-4.60, 0.0, -2.40)]
	for index in outriggers.size():
		_column(root, palette, outriggers[index], 0.85, top - 3.2, 0.15,
			"Outrigger%d" % index)
		_collars(root, palette, outriggers[index], levels.slice(0, 4), 0.24,
			"OutCollar%d_" % index)
		root.add_child(Forms.mesh_node(
			Forms.brace(outriggers[index] + Vector3(0.0, top - 3.2, 0.0),
				Vector3(0.0, top - 1.6, -3.4), 0.06, 6),
			palette.get_material("chrome"), "OutTie%d" % index))

	# One deep cantilever per module level, each with a warm collar at its
	# root and a tie-rod back up the mast. A joint the eye can follow is the
	# whole point of this variant.
	for index in levels.size():
		var y := float(levels[index])
		var arm := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.70, 0.40, 3.9), 0.12, 4),
			palette.get_material("graphite_soft"), "Arm%d" % index)
		arm.position = Vector3(0.0, y - 0.35, -2.35)
		root.add_child(arm)

		var collar := Forms.mesh_node(Forms.collar(0.52, 0.30),
			palette.get_material("gold"), "ArmCollar%d" % index, false)
		collar.position = Vector3(0.0, y - 0.35, -3.35)
		root.add_child(collar)

		root.add_child(Forms.mesh_node(
			Forms.brace(Vector3(0.0, y - 0.28, -0.55),
				Vector3(0.0, y + 1.55, -3.30), 0.055, 6),
			palette.get_material("chrome"), "Tie%d" % index))

	_post_cluster(root, palette, GAP_LOWER, 1.00, -1.45, 0.20, "Low")
	_yoke(root, palette, 10.95, 2.55, "Bowl")
	_yoke(root, palette, 14.60, 1.70, "Start")

	_ring_deck(root, palette, 7.10, 3.10, 0, "neon_orange")
	_ring_deck(root, palette, 13.95, 2.70, 2, "neon_cyan")

	_service_deck(root, palette, Vector3(0.0, 7.00, -3.20), 1.9, 2)
	_service_deck(root, palette, Vector3(0.0, 13.60, -3.20), 1.6, 3)
