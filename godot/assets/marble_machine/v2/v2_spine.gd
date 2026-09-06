extends RefCounted

## SUPPORT SYSTEM V2 - two pylons, a few big brackets, one plinth.
##
## The prior lab's tower was a lattice: dozens of thin rods, cross-braces and
## repeated collars filling the space behind and *through* the modules. It read
## as visual noise from every angle and it was the single loudest thing in the
## frame. The brief's instruction is explicit - fewer, better supports, no
## forest of scaffolding rods - so this is a family of five parts and nothing
## else:
##
##   1. PYLON     a chunky moulded column with panel breaks and a lit channel
##   2. YOKE      the horizontal beam that ties the two pylons at a level
##   3. CANTILEVER a bracket reaching from a pylon out to a module
##   4. SADDLE    the small cradle a track keel rests in
##   5. PLINTH    the stepped base the whole machine stands on
##   6. BACKWALL  the dark core slab the whole machine is built against
##   7. DECK      a small equipment platform hung off that wall
##
## ## Two pylons, placed behind
##
## At x = +/-3.30, z = -3.70 they sit outboard of the bowl's rim radius and
## behind its centre, so no column ever passes through a running surface or
## across the bowl's action clearance from any front camera. That constraint is
## what the reference actually obeys too: its dark structure is always behind
## the track, never inside it.
##
## ## Why a pylon is a moulded column and not a truss
##
## A truss is many thin edges, and many thin edges at distance become a grey
## haze that competes with the machine for attention. A column with three panel
## breaks and a recessed light channel presents four long highlights and two
## dark returns - fewer objects, more shape, and a silhouette the eye can read
## in one pass. It is also the same manufacturing language as the modules,
## which is what makes structure and shell look like one product rather than a
## toy bolted to a gantry.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")

const PYLON_X := 3.30
const PYLON_Z := -3.70
const PYLON_HALF := 0.52


static func pylon_positions() -> Array:
	return [Vector3(PYLON_X, 0.0, PYLON_Z), Vector3(-PYLON_X, 0.0, PYLON_Z)]


static func build(palette, base_y: float, top_y: float,
		panel_levels: Array) -> Node3D:
	var root := Node3D.new()
	root.name = "SpineV2"

	for entry in pylon_positions():
		var at: Vector3 = entry
		var pylon := _pylon(palette, base_y, top_y, panel_levels)
		pylon.name = "Pylon%s" % ("R" if at.x > 0.0 else "L")
		pylon.position = Vector3(at.x, 0.0, at.z)
		root.add_child(pylon)
	return root


static func _pylon(palette, base_y: float, top_y: float,
		panel_levels: Array) -> Node3D:
	## One column: a tapered shaft, panel breaks, a lit channel, a splayed foot.
	var node := Node3D.new()
	var height := top_y - base_y
	var mid := (top_y + base_y) * 0.5

	var shaft := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(PYLON_HALF * 2.0, height, PYLON_HALF * 1.55), 0.15, 4),
		palette.get_material("graphite"), "Shaft")
	shaft.position = Vector3(0.0, mid, 0.0)
	node.add_child(shaft)

	# A second, slimmer shaft standing proud on the front face. Two planes at
	# different depths is what turns a box into a moulded profile: the step
	# between them carries a hard shadow line the whole height of the machine.
	var rib := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(PYLON_HALF * 1.05, height - 0.6, PYLON_HALF * 0.5), 0.10, 3),
		palette.get_material("graphite_soft"), "FaceRib")
	rib.position = Vector3(0.0, mid, PYLON_HALF * 0.92)
	node.add_child(rib)

	# The lit channel, sunk between the shaft and the face rib.
	node.add_child(Forms.mesh_node(
		Geometry.tube([
			Vector3(0.0, base_y + 0.6, PYLON_HALF * 0.86),
			Vector3(0.0, top_y - 0.7, PYLON_HALF * 0.86)], 0.035, 8),
		palette.get_material("lit_cyan_line"), "Channel", false))

	# Panel breaks: a gold band and a graphite collar at each level where a
	# module lands. The joint-with-a-collar rule, applied vertically.
	for index in panel_levels.size():
		var y: float = float(panel_levels[index])
		var band := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(PYLON_HALF * 2.24, 0.30, PYLON_HALF * 1.80), 0.10, 3),
			palette.get_material("graphite_soft"), "Break%d" % index)
		band.position = Vector3(0.0, y, 0.0)
		node.add_child(band)

		var trim := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(PYLON_HALF * 2.30, 0.055, PYLON_HALF * 1.86), 0.02, 2),
			palette.get_material("gold"), "BreakTrim%d" % index, false)
		trim.position = Vector3(0.0, y + 0.17, 0.0)
		node.add_child(trim)

	var foot := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(PYLON_HALF * 3.0, 0.52, PYLON_HALF * 2.5), 0.16, 4),
		palette.get_material("graphite_deep"), "Foot")
	foot.position = Vector3(0.0, base_y + 0.20, 0.0)
	node.add_child(foot)
	return node


static func backwall(palette, base_y: float, top_y: float,
		panel_levels: Array) -> Node3D:
	## The dark architecture the modules are built against.
	##
	## Two pylons and three yokes leave the middle of the frame empty, and an
	## empty middle is what made the machine read as thin: the gorge showed
	## straight through the gaps between modules and every bright shell was
	## being read against a different background at every height. The
	## reference solves this with a solid core - look past its track and there
	## is a continuous dark mass behind the whole tower.
	##
	## It is a single stepped slab with recessed panels rather than a truss,
	## for the same reason a pylon is: at this distance a lattice becomes grey
	## haze, and a slab becomes depth. It sits at z = -4.6, behind the pylons
	## themselves, so it can never occlude anything.
	var node := Node3D.new()
	node.name = "BackWall"
	var height := top_y - base_y
	var mid := (top_y + base_y) * 0.5
	var z := PYLON_Z - 0.85

	var slab := Forms.mesh_node(
		Geometry.rounded_box(Vector3(PYLON_X * 1.86, height, 0.90), 0.22, 4),
		palette.get_material("graphite"), "Slab")
	slab.position = Vector3(0.0, mid, z)
	node.add_child(slab)

	# Two shallower wings, stepped back, so the wall has a silhouette of its
	# own rather than being one rectangle.
	for side in [1.0, -1.0]:
		var wing := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(1.30, height * 0.78, 0.62), 0.18, 3),
			palette.get_material("graphite"),
			"Wing%s" % ("R" if side > 0.0 else "L"))
		wing.position = Vector3(side * (PYLON_X * 0.93 + 0.30),
			mid - height * 0.06, z - 0.20)
		node.add_child(wing)

	# Recessed panels: a lighter inset with a gold sill under each. Regular
	# and banded, so they read as one texture and not as scattered detail.
	for index in panel_levels.size():
		var y: float = float(panel_levels[index])
		var inset := Forms.mesh_node(
			Geometry.rounded_box(Vector3(PYLON_X * 1.40, 1.05, 0.16), 0.10, 3),
			palette.get_material("graphite_soft"), "Panel%d" % index)
		inset.position = Vector3(0.0, y + 0.9, z + 0.50)
		node.add_child(inset)

		var sill := Forms.mesh_node(
			Geometry.rounded_box(Vector3(PYLON_X * 1.46, 0.09, 0.22), 0.03, 2),
			palette.get_material("gold"), "PanelSill%d" % index, false)
		sill.position = Vector3(0.0, y + 0.32, z + 0.52)
		node.add_child(sill)

		var glow := Forms.mesh_node(
			Geometry.tube([
				Vector3(-PYLON_X * 0.62, y + 1.36, z + 0.58),
				Vector3(PYLON_X * 0.62, y + 1.36, z + 0.58)], 0.030, 8),
			palette.get_material("lit_cyan"), "PanelLight%d" % index, false)
		node.add_child(glow)

	# Vertical louvres across the slab's face. The wall was reading as one
	# black rectangle with a few orange dots on it: at this size a surface
	# needs a direction as well as a value, and a regular set of shallow
	# uprights gives it one without adding a single silhouette edge.
	var louvre := Geometry.rounded_box(
		Vector3(0.22, height - 1.4, 0.20), 0.07, 3)
	for index in 9:
		var x: float = (float(index) - 4.0) * PYLON_X * 0.195
		var fin := Forms.mesh_node(louvre,
			palette.get_material("graphite_deep"), "Louvre%d" % index)
		fin.position = Vector3(x, mid, z + 0.52)
		node.add_child(fin)

	for side in [1.0, -1.0]:
		node.add_child(Forms.mesh_node(
			Geometry.tube([
				Vector3(side * PYLON_X * 0.88, base_y + 0.8, z + 0.60),
				Vector3(side * PYLON_X * 0.88, top_y - 0.8, z + 0.60)], 0.035, 8),
			palette.get_material("lit_cyan"),
			"WallLight%s" % ("R" if side > 0.0 else "L"), false))

	var cap := Forms.mesh_node(
		Geometry.rounded_box(Vector3(PYLON_X * 2.02, 0.46, 1.20), 0.16, 4),
		palette.get_material("graphite_soft"), "Cap")
	cap.position = Vector3(0.0, top_y - 0.10, z)
	node.add_child(cap)

	var capTrim := Forms.mesh_node(
		Geometry.rounded_box(Vector3(PYLON_X * 2.06, 0.07, 1.26), 0.03, 2),
		palette.get_material("gold"), "CapTrim", false)
	capTrim.position = Vector3(0.0, top_y + 0.16, z)
	node.add_child(capTrim)
	return node


static func deck(palette, at: Vector3, span: float, seed_index: int,
		node_name: String) -> Node3D:
	## A small equipment platform hung off the core wall.
	##
	## The machinery read, and the thing that fills the vertical gaps between
	## modules. Two of these carry more density than twenty braces would,
	## because they are objects with a top, a front and a shadow rather than
	## lines that cross other lines.
	var node := Node3D.new()
	node.name = node_name
	node.position = at

	node.add_child(Forms.mesh_node(
		Geometry.rounded_box(Vector3(span, 0.24, 1.15), 0.09, 3),
		palette.get_material("graphite_soft"), "Floor"))
	node.add_child(Forms.mesh_node(
		Geometry.rounded_box(Vector3(span + 0.16, 0.10, 1.28), 0.04, 2),
		palette.get_material("gold"), "Edge"))

	var rack := Node3D.new()
	rack.name = "Rack"
	rack.position = Vector3(0.0, 0.12, 0.05)
	node.add_child(rack)
	Forms.equipment_rack(rack, palette.get_material("graphite"),
		palette.get_material("orange_machine"),
		palette.get_material("lit_cyan_line"), seed_index, span - 0.7)

	for side in [1.0, -1.0]:
		var drum := Forms.mesh_node(
			Geometry.rounded_disc(0.26, 0.40, 0.09, 18, 3),
			palette.get_material("orange_machine"),
			"Drum%s" % ("R" if side > 0.0 else "L"))
		drum.position = Vector3(side * (span * 0.5 - 0.18), 0.28, -0.10)
		drum.rotation.z = PI * 0.5
		node.add_child(drum)
	return node

static func yoke(palette, y: float, node_name: String) -> Node3D:
	## The beam tying the two pylons at one level, plus its two collars.
	var node := Node3D.new()
	node.name = node_name

	var beam := Forms.mesh_node(
		Geometry.rounded_box(Vector3(PYLON_X * 2.0 - 0.2, 0.40, 0.52), 0.16, 4),
		palette.get_material("graphite_soft"), "Beam")
	beam.position = Vector3(0.0, y, PYLON_Z)
	node.add_child(beam)

	for side in [1.0, -1.0]:
		var collar := Forms.mesh_node(
			Geometry.rounded_disc(0.30, 0.22, 0.08, 20, 3),
			palette.get_material("gold"),
			"YokeCollar%s" % ("R" if side > 0.0 else "L"), false)
		collar.position = Vector3(side * (PYLON_X - 0.34), y, PYLON_Z)
		collar.rotation.z = PI * 0.5
		node.add_child(collar)
	return node


static func cantilever(palette, from_side: float, y: float, reach: Vector3,
		node_name: String) -> Node3D:
	## A bracket from one pylon out to a module: a tapered arm, a gold collar
	## at the pylon, and an orange jack under it.
	##
	## The shape is a wedge rather than a rod because a bracket is loaded in
	## bending and looks wrong when it is not - and because a wedge presents a
	## broad face to the key light, which is what stops the structure
	## disappearing into its own shadow.
	var node := Node3D.new()
	node.name = node_name
	var root_at := Vector3(from_side * PYLON_X, y, PYLON_Z)
	var span := reach - root_at
	var length := span.length()
	var mid := root_at + span * 0.5

	var arm := Forms.mesh_node(
		Geometry.rounded_box(Vector3(length, 0.42, 0.48), 0.15, 4),
		palette.get_material("graphite"), "Arm")
	arm.position = mid
	arm.rotation.y = atan2(-span.z, span.x)
	arm.rotation.z = asin(clampf(span.y / maxf(length, 0.001), -1.0, 1.0))
	node.add_child(arm)

	var collar := Forms.mesh_node(
		Geometry.rounded_disc(0.32, 0.26, 0.09, 20, 3),
		palette.get_material("gold"), "Collar")
	collar.position = root_at + span.normalized() * 0.30
	collar.rotation.z = PI * 0.5
	collar.rotation.y = atan2(-span.z, span.x)
	node.add_child(collar)

	var jack := Forms.mesh_node(
		Geometry.rounded_disc(0.15, 0.40, 0.06, 16, 3),
		palette.get_material("orange_machine"), "Jack")
	jack.position = mid + Vector3(0.0, -0.34, 0.0)
	jack.rotation.z = PI * 0.5
	jack.rotation.y = atan2(-span.z, span.x)
	node.add_child(jack)
	return node


static func saddle(palette, at: Vector3, heading: float,
		node_name: String) -> Node3D:
	## The small cradle a track keel rests in where it crosses a support.
	##
	## Two of these under the S are what makes the track look *carried*. A
	## track that meets its supports without a fitting reads as a floating
	## ribbon that happens to touch a post.
	var node := Node3D.new()
	node.name = node_name
	node.position = at
	node.rotation.y = heading

	node.add_child(Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.24, 0.30, 0.62), 0.12, 4),
		palette.get_material("graphite_soft"), "Bed"))
	for side in [1.0, -1.0]:
		var cheek := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.20, 0.46, 0.58), 0.08, 3),
			palette.get_material("graphite"),
			"Cheek%s" % ("R" if side > 0.0 else "L"))
		cheek.position = Vector3(side * 0.60, 0.20, 0.0)
		node.add_child(cheek)
		var bolt := Forms.mesh_node(
			Geometry.rounded_disc(0.11, 0.10, 0.04, 14, 2),
			palette.get_material("gold"),
			"SaddleBolt%s" % ("R" if side > 0.0 else "L"), false)
		bolt.position = Vector3(side * 0.60, 0.30, 0.32)
		bolt.rotation.x = PI * 0.5
		node.add_child(bolt)
	return node


static func plinth(palette, y: float) -> Node3D:
	## The stepped base. Two tiers, a gold inlay, a cyan edge, and hardware.
	##
	## Its job is to stop the machine floating - the marble-v1 complaint - and
	## it does that by being wider than anything above it and by casting the
	## one large soft shadow in the frame. It also gives the warm bounce a
	## surface to come off, which is where the machine's underside light
	## comes from.
	var node := Node3D.new()
	node.name = "Plinth"
	node.position = Vector3(0.0, y, 0.0)

	node.add_child(Forms.mesh_node(
		Geometry.rounded_disc(3.75, 0.56, 0.19, 56, 4),
		palette.get_material("graphite_deep"), "Lower"))

	var upper := Forms.mesh_node(
		Geometry.rounded_disc(3.00, 0.42, 0.15, 56, 4),
		palette.get_material("graphite"), "Upper")
	upper.position = Vector3(0.0, 0.48, 0.0)
	node.add_child(upper)

	var deck := Forms.mesh_node(
		Geometry.rounded_disc(2.42, 0.16, 0.07, 48, 3),
		palette.get_material("graphite_soft"), "Deck")
	deck.position = Vector3(0.0, 0.74, 0.0)
	node.add_child(deck)

	# A warm ring recessed into the deck. The bottom of the frame was reading
	# as one dead disc; a lit ring gives it a centre, and it is also the
	# source the whole machine's underside light is meant to be coming from.
	var hearth := Forms.mesh_node(
		Forms.hoop(1.92, 0.075, 56, 8), palette.get_material("lit_gold"),
		"Hearth", false)
	hearth.position = Vector3(0.0, 0.80, 0.0)
	node.add_child(hearth)

	var inlay := Forms.mesh_node(
		Forms.hoop(2.68, 0.06, 64, 8), palette.get_material("gold"),
		"Inlay", false)
	inlay.position = Vector3(0.0, 0.70, 0.0)
	node.add_child(inlay)

	var edge := Forms.mesh_node(
		Forms.hoop(3.73, 0.06, 72, 8), palette.get_material("lit_cyan_line"),
		"EdgeLight", false)
	edge.position = Vector3(0.0, 0.22, 0.0)
	node.add_child(edge)

	Forms.bolt_ring(node, palette.get_material("chrome"), 24, 3.40, 0.30,
		0.075, 0.065)

	# Four orange service blocks around the rim: the machinery read at the
	# base, and the warm anchor the brief asks for at the bottom of the frame.
	for index in 4:
		var bearing := deg_to_rad(46.0 + 90.0 * float(index))
		var direction := Vector3(cos(bearing), 0.0, sin(bearing))
		var block := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.76, 0.40, 0.56), 0.13, 3),
			palette.get_material("orange_machine"), "Service%d" % index)
		block.position = direction * 3.14 + Vector3(0.0, 0.50, 0.0)
		block.rotation.y = -bearing
		node.add_child(block)
	return node
