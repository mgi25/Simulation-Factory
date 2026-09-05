extends RefCounted

## The descending S: a moulded channel, guarded, lit and hung off the tower.
##
## The brief's requirement is that this looks like a part that could physically
## come in a box, and the failure mode it names - "sampled/ribbon appearance" -
## has a specific cause. A ribbon is what you get when a track is one surface.
## A moulded channel is five, stacked in section:
##
##     silver top lip        <- catches the key, draws the edge
##     acrylic side guard    <- transparent, stands proud of the wall
##     pearl channel         <- the running surface and its walls
##     gold fascia           <- the warm band under the lip
##     graphite keel         <- the dark structural spine
##
## Every one of those is a separate sweep along the same spline, offset in the
## path's own frame so they can never drift apart. Seen from the hero camera
## the stack is perhaps twelve pixels deep, and those twelve pixels are the
## difference between a drawn line and an extruded component. The style-lock
## track had three of the five and no transparent element at all.
##
## ## Why a spline and not an arc chain
##
## An arc chain has a curvature step at every joint, and a glossy channel
## shows a curvature step as a kink in its highlight. Catmull-Rom through
## authored controls is continuous, so the highlight runs the length of the
## track unbroken - which is exactly the shot the concept sells its S-curve
## bridge on.
##
## The module works in its parent's space: it is handed world-space controls
## because a track's whole job is to connect two other modules, and a local
## origin would only have to be undone.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")

const HALF_WIDTH := 0.40
const WALL_HEIGHT := 0.25
const SAMPLES := 14


static func path_for(controls: Array) -> Array:
	## The running centreline, at the density everything else is built on.
	return Forms.smooth_path(controls, SAMPLES)


static func build(palette, controls: Array, node_name := "SCurve",
		accent := "neon_cyan") -> Node3D:
	var root := Node3D.new()
	root.name = node_name
	var path := path_for(controls)

	_channel(root, palette, path)
	_understructure(root, palette, path)
	_guards(root, palette, path)
	_neon(root, palette, path, accent)
	_supports(root, palette, path)

	return root


# --- the five layers ------------------------------------------------------

static func _channel(root: Node3D, palette, path: Array) -> void:
	## The pearl running surface, walls and outer flanks, as one solid.
	var section: Array = Geometry.channel_section(
		HALF_WIDTH, 0.17, WALL_HEIGHT, 0.10, 4)
	root.add_child(Forms.mesh_node(
		Geometry.sweep(path, section[0], section[1], true),
		palette.get_material("track_silver"), "Channel"))

	# The silver lip along the top of each wall. Round stock, because a wall
	# that ends in a flat edge catches a one-pixel highlight and one in round
	# stock catches a band - the same argument the whole rounding toolkit
	# rests on, applied to the longest edge in the machine.
	for side in 2:
		var lateral: float = HALF_WIDTH * (1.0 if side == 0 else -1.0)
		var lip_path := Forms.offset_path(path, lateral, WALL_HEIGHT)
		root.add_child(Forms.mesh_node(
			Geometry.tube(lip_path, 0.042, 8),
			palette.get_material("pearl_lip"), "TopLip%d" % side, false))


static func _understructure(root: Node3D, palette, path: Array) -> void:
	## Warm fascia over dark keel: the 1:5 structure-to-track value split the
	## concept builds every one of its beams from.
	var fascia_section: Array = Geometry.beam_section(HALF_WIDTH - 0.05, 0.20, 0.06, 3)
	root.add_child(Forms.mesh_node(
		Geometry.sweep(Forms.offset_path(path, 0.0, -0.28),
			fascia_section[0], fascia_section[1], true),
		palette.get_material("gold"), "Fascia", false))

	var keel_section: Array = Geometry.beam_section(HALF_WIDTH - 0.19, 0.30, 0.09, 3)
	root.add_child(Forms.mesh_node(
		Geometry.sweep(Forms.offset_path(path, 0.0, -0.53),
			keel_section[0], keel_section[1], true),
		palette.get_material("graphite_deep"), "Keel"))

	# The underlight, tucked in the shadow between fascia and keel.
	root.add_child(Forms.mesh_node(
		Geometry.tube(Forms.offset_path(path, 0.0, -0.41), 0.030, 6),
		palette.get_material("lit_cyan_soft"), "UnderLight", false))


static func _guards(root: Node3D, palette, path: Array) -> void:
	## Acrylic standing proud of the channel walls, on its own shoulder.
	var height: float = 0.40
	if palette.variant == "deck":
		height = 0.32
	var guard_section: Array = Geometry.beam_section(0.035, height, 0.014, 2)
	var key := "acrylic_aqua_deep" if palette.variant == "deck" else "acrylic_aqua"

	for side in 2:
		var lateral: float = (HALF_WIDTH + 0.045) * (1.0 if side == 0 else -1.0)
		var guard_path := Forms.offset_path(path, lateral,
			WALL_HEIGHT + height * 0.5 - 0.06)
		root.add_child(Forms.mesh_node(
			Geometry.sweep(guard_path, guard_section[0], guard_section[1], true),
			palette.get_material(key), "Guard%d" % side, false))

		# A clear cap on the guard's top edge, for the same reason the bowl's
		# guard has one: cast acrylic has a bright edge, and without it the
		# panel has no silhouette against a dark background.
		root.add_child(Forms.mesh_node(
			Geometry.tube(
				Forms.offset_path(path, lateral, WALL_HEIGHT + height - 0.06),
				0.026, 6),
			palette.get_material("acrylic_clear"), "GuardCap%d" % side, false))

	# Guard posts at intervals, alternating sides: the medium-scale rhythm
	# along a length of track that would otherwise be one smooth extrusion.
	var post := Geometry.rounded_box(Vector3(0.07, height + 0.30, 0.11), 0.025, 3)
	var count := 7
	for index in count:
		var t := (float(index) + 0.5) / float(count)
		var side_sign: float = 1.0 if index % 2 == 0 else -1.0
		var lateral := (HALF_WIDTH + 0.05) * side_sign
		var at := Forms.sample_at(Forms.offset_path(path, lateral, 0.0), t)
		var node := Forms.mesh_node(post, palette.get_material("silver_deep"),
			"GuardPost%d" % index, false)
		node.position = at + Vector3(0.0, (height + 0.30) * 0.5 - 0.14, 0.0)
		root.add_child(node)


static func _neon(root: Node3D, palette, path: Array, accent: String) -> void:
	## The zone light: a rope of neon down both flanks, outboard of the wall.
	##
	## This is the reference's signature and the thing every earlier prototype
	## left out. Its track is not a light-coloured surface with a glow pass
	## over it - it is a dark-mounted channel with a *lit edge* running the
	## whole length, and the eye follows that edge from module to module. A
	## soft strip tucked under the fascia cannot do that job: it has to sit on
	## the silhouette, at an emission high enough to cross the bloom threshold
	## on its own.
	##
	## The accent is per-chute, so the run reads as zones - cyan at the top,
	## violet through the mixer, warm at the finish - which is the concept's
	## own colour plan and the reason its tower does not read as monochrome.
	for side in 2:
		var lateral: float = (HALF_WIDTH + 0.085) * (1.0 if side == 0 else -1.0)
		root.add_child(Forms.mesh_node(
			Geometry.tube(
				Forms.offset_path(path, lateral, WALL_HEIGHT - 0.10), 0.048, 8),
			palette.get_material(accent), "Neon%d" % side, false))


static func _supports(root: Node3D, palette, path: Array) -> void:
	## Where the track is held. Three brackets, each a collar, a leg and a tie.
	var count := 3
	for index in count:
		var t := (float(index) + 0.6) / float(count + 0.4)
		var at := Forms.sample_at(path, t)
		var anchor := Vector3(at.x * 0.14, at.y - 2.15, at.z * 0.14 - 0.55)

		var collar := Forms.mesh_node(Forms.collar(0.30, 0.16),
			palette.get_material("gold"), "SupportCollar%d" % index, false)
		collar.position = at + Vector3(0.0, -0.55, 0.0)
		root.add_child(collar)

		root.add_child(Forms.mesh_node(
			Forms.brace(at + Vector3(0.0, -0.55, 0.0), anchor, 0.075, 8),
			palette.get_material("graphite"), "SupportLeg%d" % index))

		root.add_child(Forms.mesh_node(
			Forms.brace(at + Vector3(0.0, -0.30, 0.0),
				anchor.lerp(at, 0.30) + Vector3(0.0, 0.55, 0.0), 0.038, 6),
			palette.get_material("chrome"), "SupportTie%d" % index))
