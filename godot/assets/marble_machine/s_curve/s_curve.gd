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
		accent := "neon_cyan", mounts: Dictionary = {}) -> Node3D:
	## `mounts` is what the chute is told about the machine around it:
	##
	##     "anchors"  uprights a bracket may reach to, from `Tower.anchors`
	##     "clear"    protected volumes nothing of this chute may enter
	##
	## Both are optional and both default to the module's old behaviour, so a
	## chute in open air still builds exactly as it did.
	var root := Node3D.new()
	root.name = node_name
	var path := path_for(controls)
	var volumes: Array = mounts.get("clear", [])

	_channel(root, palette, path)
	_understructure(root, palette, path, volumes)
	_guards(root, palette, path)
	_neon(root, palette, path, accent)
	_supports(root, palette, path, mounts.get("anchors", []), volumes)

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


static func _understructure(root: Node3D, palette, path: Array,
		volumes: Array) -> void:
	## Warm fascia over dark keel: the 1:5 structure-to-track value split the
	## concept builds every one of its beams from.
	##
	## The spine stops short of any protected volume. A chute that ends over a
	## bowl hangs two thirds of a unit of dark structure below its running
	## line, and that is precisely the depth the bowl's mouth occupies: the
	## first hero frame had the feed chute's keel driven into the dish like a
	## bar. Trimming it and cantilevering the last stretch is what a moulded
	## delivery lip does anyway, and the cut end gets a nose so it reads as
	## finished rather than broken off.
	var spine := Forms.longest_clear_run(path, 0.18, 0.70, volumes)
	if spine.size() < 4:
		spine = path

	var fascia_section: Array = Geometry.beam_section(HALF_WIDTH - 0.05, 0.20, 0.06, 3)
	root.add_child(Forms.mesh_node(
		Geometry.sweep(Forms.offset_path(spine, 0.0, -0.28),
			fascia_section[0], fascia_section[1], true),
		palette.get_material("gold"), "Fascia", false))

	var keel_section: Array = Geometry.beam_section(HALF_WIDTH - 0.19, 0.30, 0.09, 3)
	root.add_child(Forms.mesh_node(
		Geometry.sweep(Forms.offset_path(spine, 0.0, -0.53),
			keel_section[0], keel_section[1], true),
		palette.get_material("graphite_deep"), "Keel"))

	# The underlight, tucked in the shadow between fascia and keel.
	root.add_child(Forms.mesh_node(
		Geometry.tube(Forms.offset_path(spine, 0.0, -0.41), 0.030, 6),
		palette.get_material("lit_cyan_soft"), "UnderLight", false))

	if spine.size() < path.size():
		_noses(root, palette, path, spine)


static func _noses(root: Node3D, palette, path: Array, spine: Array) -> void:
	## A cap on each end the spine was cut back to.
	for which in 2:
		var edge: Vector3 = spine[0] if which == 0 else spine[spine.size() - 1]
		if edge.is_equal_approx(path[0]) or edge.is_equal_approx(
				path[path.size() - 1]):
			continue
		var cap := Forms.mesh_node(
			Geometry.rounded_box(Vector3(HALF_WIDTH * 1.5, 0.30, 0.26), 0.09, 3),
			palette.get_material("silver_deep"), "SpineNose%d" % which)
		cap.position = edge + Vector3(0.0, -0.38, 0.0)
		root.add_child(cap)

		var boss := Forms.mesh_node(Forms.collar(0.17, 0.11),
			palette.get_material("gold"), "SpineNoseBoss%d" % which, false)
		boss.position = edge + Vector3(0.0, -0.24, 0.0)
		root.add_child(boss)


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


static func _supports(root: Node3D, palette, path: Array, anchors: Array,
		volumes: Array) -> void:
	## Where the track is held. Three brackets, each a collar, a leg and a tie.
	##
	## The leg reaches *outward*, to the nearest upright the frame published,
	## and not inward toward the machine's axis. The old inward rule aimed
	## every leg at a point in the middle of the air - there is no column on
	## the axis of this machine, the frame stands behind the run - and where
	## the chute happened to pass over a module the leg simply landed in it.
	## Two of the feed chute's three brackets ended inside the bowl.
	##
	## A bracket that still cannot be built without entering a protected
	## volume is dropped rather than moved somewhere it does not belong. Three
	## is the number that looks right, not a number the module owes anyone.
	var count := 3
	for index in count:
		var t := (float(index) + 0.6) / float(count + 0.4)
		var at := Forms.sample_at(path, t)
		var anchor := _bracket_foot(at, anchors, volumes)
		var head := at + Vector3(0.0, -0.55, 0.0)
		# The collar has a body of its own. Testing only the leg lets a
		# bracket whose leg rises clear of a volume still hang its fitting
		# four centimetres into one.
		if not Forms.segment_clears_all(head + Vector3(0.0, 0.17, 0.0),
				head - Vector3(0.0, 0.17, 0.0), volumes):
			continue
		if not Forms.segment_clears_all(head, anchor, volumes):
			continue

		var collar := Forms.mesh_node(Forms.collar(0.30, 0.16),
			palette.get_material("gold"), "SupportCollar%d" % index, false)
		collar.position = head
		root.add_child(collar)

		root.add_child(Forms.mesh_node(
			Forms.brace(head, anchor, 0.075, 8),
			palette.get_material("graphite"), "SupportLeg%d" % index))

		var tie_end := anchor.lerp(at, 0.30) + Vector3(0.0, 0.55, 0.0)
		if not Forms.segment_clears_all(
				at + Vector3(0.0, -0.30, 0.0), tie_end, volumes):
			continue
		root.add_child(Forms.mesh_node(
			Forms.brace(at + Vector3(0.0, -0.30, 0.0), tie_end, 0.038, 6),
			palette.get_material("chrome"), "SupportTie%d" % index))


static func _bracket_foot(at: Vector3, anchors: Array,
		volumes: Array) -> Vector3:
	## Where one bracket's leg lands.
	##
	## Four fifths of the way to the nearest published upright, dropped a
	## fixed reach - and then lifted back up if that drop would have ended the
	## leg inside a protected volume. Shortening a bracket keeps it; only a
	## bracket that cannot clear the volume at any length is abandoned.
	if anchors.is_empty():
		return Vector3(at.x * 0.14, at.y - 2.15, at.z * 0.14 - 0.55)

	var best: Vector3 = anchors[0]
	var closest := INF
	for candidate in anchors:
		var distance := Vector2(at.x - candidate.x,
			at.z - candidate.z).length_squared()
		if distance < closest:
			closest = distance
			best = candidate

	var foot := Vector3(lerpf(at.x, best.x, 0.80), at.y - 1.55,
		lerpf(at.z, best.z, 0.80))
	var ceiling := Forms.ceiling_above(foot, volumes)
	if ceiling > foot.y:
		foot.y = minf(ceiling + 0.30, at.y - 0.35)
	return foot
