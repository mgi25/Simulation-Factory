extends RefCounted

## The five race moments that are built rather than driven through.
##
## Every builder returns a node in its own frame: **+Z is downhill**, +Y is up,
## and the origin sits on the channel centreline. `course_machine` places each
## one at its anchor and yaws it to the direction of travel there, so a module
## never has a world coordinate in it and the whole set survives the course
## being re-routed.
##
## ## What each one is for
##
##     start      eight racers abreast, one gate, one fan into the channel
##     mixer      a compact order-shuffler, deliberately subordinate
##     obstacle   a spinner corridor: the one mechanical event on the course
##     split      the choice, as a wedge with two identities
##     merge      the compression that hands the field to the final run
##
## The start is the one that changed most from the tower build. That start was
## a pod with a mixing housing slung under its deck and a throat that dropped
## the field into a bowl - correct for a machine, wrong for a race. This one is
## a *starting grid*: a wide shallow shelf, eight visible bays, a gate across
## all of them, and a fan that turns eight lanes into one channel over four
## units of open track. The mechanism that removes lane bias is a separate,
## smaller thing further down the hill, which is what keeps the line ceremonial.
##
## Fairness is **unverified**. Nothing here simulates, and the fan is a shape,
## not a proof. See `docs/validation/sloped_course/physics_layout.json`.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Track := preload("res://assets/marble_machine/v2/v2_track.gd")

const BAYS := 8
const BAY_PITCH := 0.63
const FIN_THICK := 0.07
const DECK_TOP := 0.0          # the surface a waiting racer rests on
const POD_WIDTH := 6.30
const POD_HEIGHT := 1.10
const GROOVE_LENGTH := 3.40
const MARBLE_RADIUS := 0.285


static func bay_x(index: int) -> float:
	return (float(index) - float(BAYS - 1) * 0.5) * BAY_PITCH


# --- START ----------------------------------------------------------------


static func start(palette, exit_local: Vector3) -> Node3D:
	## The starting grid. `exit_local` is where the first run begins, in the
	## module's own frame - the fan is built to land exactly on it.
	var root := Node3D.new()
	root.name = "Start"

	_start_pod(root, palette)
	_start_bays(root, palette, exit_local)
	_start_gate(root, palette)
	_start_field(root, palette)
	sign_panel(root, palette, "START", 4.6,
		Vector3(0.0, 2.06, -GROOVE_LENGTH - 0.86), "sign_face", "lit_white")
	_skirt(root, palette, POD_WIDTH * 0.74, GROOVE_LENGTH * 0.54, -1.06, 3.4,
		-GROOVE_LENGTH - GROOVE_LENGTH * 0.21)
	return root


static func _start_pod(root: Node3D, palette) -> void:
	## The moulded block the grid is cut into: one body, one big fillet.
	var depth := GROOVE_LENGTH * 0.62
	var at := -GROOVE_LENGTH - depth * 0.34
	var body := Forms.mesh_node(
		Geometry.rounded_box(Vector3(POD_WIDTH, POD_HEIGHT, depth), 0.30, 4),
		palette.get_material("pearl_shell"), "Body")
	body.position = Vector3(0.0, DECK_TOP - POD_HEIGHT * 0.5 - 0.06, at)
	root.add_child(body)

	var lip := Forms.mesh_node(
		Geometry.rounded_box(Vector3(POD_WIDTH + 0.16, 0.18, depth + 0.16),
			0.08, 4),
		palette.get_material("pearl_lip_v2"), "Lip", false)
	lip.position = Vector3(0.0, DECK_TOP + 0.20, at)
	root.add_child(lip)

	var band := Forms.mesh_node(
		Geometry.rounded_box(Vector3(POD_WIDTH - 0.40, 0.11, depth + 0.22),
			0.05, 3),
		palette.get_material("lit_cyan_line_hero"), "Band", false)
	band.position = Vector3(0.0, DECK_TOP - 0.36, at)
	root.add_child(band)


static func _start_bays(root: Node3D, palette, exit_local: Vector3) -> void:
	## The grid itself: a tapering trough, eight lanes, seven fins.
	##
	## The convergence happens *on the deck*, the way it does on the real
	## sample - eight parallel grooves that bend inward and become one chute at
	## the lip. The first build did it the other way round, opening the running
	## channel out to two and a half times its width for four units, and the
	## flare that produced was a white shell that swallowed the pod it was
	## supposed to be leaving.
	var back_half := POD_WIDTH * 0.5 - 0.42
	var front_half := 1.02
	var samples := 40
	var path: Array = []
	var sections: Array = []
	var normals: Array = []
	var banks: Array = []
	var back := Vector3(0.0, DECK_TOP - 0.02, -GROOVE_LENGTH)
	var front := exit_local
	for index in samples:
		var t := float(index) / float(samples - 1)
		var eased := smoothstep(0.10, 1.0, t)
		path.append(back.lerp(front, t))
		var built := trough_section(lerpf(back_half, front_half, eased))
		sections.append(built[0])
		normals.append(built[1])
		banks.append(0.0)

	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, sections, normals, banks),
		palette.get_material("pearl_shell"), "Deck"))

	# The running surface, a hair inside the trough and in the polished metal
	# the channel uses - so the racers stand on the same material they will
	# run on for the next two hundred units.
	var inner: Array = []
	var inner_normals: Array = []
	for index in samples:
		var t := float(index) / float(samples - 1)
		var eased := smoothstep(0.10, 1.0, t)
		var built := floor_section(lerpf(back_half, front_half, eased) - 0.05)
		inner.append(built[0])
		inner_normals.append(built[1])
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, inner, inner_normals, banks),
		palette.get_material("running_polished"), "Grid", false))

	# Seven fins, each following its own lane inward. Round stock rather than
	# blades: a rib catches one highlight down its whole length, and that is
	# what keeps eight lanes legible at phone size.
	for index in BAYS - 1:
		var lane: Array = []
		for step in samples:
			var t := float(step) / float(samples - 1)
			var eased := smoothstep(0.10, 1.0, t)
			var spread := lerpf(back_half, front_half, eased) / back_half
			var centre: Vector3 = path[step]
			lane.append(Vector3((bay_x(index) + BAY_PITCH * 0.5) * spread,
				centre.y + 0.08, centre.z))
		root.add_child(Forms.mesh_node(Geometry.tube(lane, 0.055, 8),
			palette.get_material("pearl_lip_v2"), "Fin%d" % index, false))

	for side in [1.0, -1.0]:
		var suffix := "R" if side > 0.0 else "L"
		var rail: Array = []
		var line: Array = []
		for step in samples:
			var t := float(step) / float(samples - 1)
			var eased := smoothstep(0.10, 1.0, t)
			var half := lerpf(back_half, front_half, eased)
			var centre: Vector3 = path[step]
			rail.append(Vector3(side * (half + 0.16), centre.y + 0.34,
				centre.z))
			line.append(Vector3(side * (half + 0.21), centre.y + 0.02,
				centre.z))
		root.add_child(Forms.mesh_node(Geometry.tube(rail, 0.075, 10),
			palette.get_material("chrome"), "Rail%s" % suffix, false))
		root.add_child(Forms.mesh_node(Geometry.tube(line, 0.05, 8),
			palette.get_material("lit_cyan_line_hero"), "Line%s" % suffix,
			false))


static func _start_field(root: Node3D, palette) -> void:
	## Eight racers on the line: the claim the whole module exists to make.
	var sphere := SphereMesh.new()
	sphere.radius = MARBLE_RADIUS
	sphere.height = MARBLE_RADIUS * 2.0
	sphere.radial_segments = 24
	sphere.rings = 12
	for index in BAYS:
		var racer := MeshInstance3D.new()
		racer.name = "Waiting%d" % index
		racer.mesh = sphere
		racer.material_override = palette.marble(index)
		racer.position = Vector3(bay_x(index),
			DECK_TOP - 0.30 + MARBLE_RADIUS, -GROOVE_LENGTH + 0.66)
		root.add_child(racer)


static func _start_gate(root: Node3D, palette) -> void:
	## One bar across all eight bays, with the machinery that lifts it.
	var half := POD_WIDTH * 0.5 - 0.42
	var z := -GROOVE_LENGTH + 0.18
	root.add_child(Forms.mesh_node(
		Geometry.tube([Vector3(-half - 0.10, DECK_TOP + 0.26, z),
			Vector3(half + 0.10, DECK_TOP + 0.26, z)], 0.085, 12),
		palette.get_material("chrome"), "GateBar", false))

	for index in BAYS:
		var paddle := Forms.mesh_node(
			Geometry.rounded_box(Vector3(BAY_PITCH - 0.12, 0.42, 0.09),
				0.035, 3),
			palette.get_material("orange_machine"), "Paddle%d" % index, false)
		paddle.position = Vector3(bay_x(index), DECK_TOP + 0.06, z)
		root.add_child(paddle)

	for side in [1.0, -1.0]:
		var suffix := "R" if side > 0.0 else "L"
		var housing := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.62, 0.86, 0.72), 0.18, 3),
			palette.get_material("graphite"), "GateBox%s" % suffix)
		housing.position = Vector3(side * (half + 0.30), DECK_TOP + 0.16, z)
		root.add_child(housing)
		var drum := Forms.mesh_node(
			Geometry.rounded_disc(0.22, 0.18, 0.05, 18, 3),
			palette.get_material("gold"), "GateDrum%s" % suffix, false)
		drum.position = Vector3(side * (half + 0.30), DECK_TOP + 0.34, z)
		drum.rotation.z = PI * 0.5
		root.add_child(drum)


# --- SHUFFLE START (V1.17) -------------------------------------------------
#
# The start the physics actually runs, drawn from the physics' own numbers.
#
# `sloped.trapdoor.ShuffleFloor` replaced the V1 fan pod in V1.8 - eight bays on
# a sloping apron, a round mixing chamber with a four-blade rotor, a louvre
# trapdoor floor, a catch cone and an exit chute - and `start()` above was never
# updated, so the render drew the old pod at `layout.NODES["start"]` while the
# field stood `lift` = 3.93 layout units above it. The eight racers hung in
# mid-air for the first four seconds of every video shipped since V1.9.
#
# **Nothing here is authored.** Every dimension comes from the contract
# `tools/sloped_start_contract.py` reads off the built module, and the eight
# gate paddles, four rotor blades and eighteen floor slats are not built as
# mechanisms at all: they are boxes at the sizes the solver was given, driven
# frame by frame from the transforms `marble3d.replay` already records for them.
# So there is no release law, no mixing law and no trapdoor law in the renderer
# for a future physics change to leave behind.
#
# The one number that is NOT a defect: the bay pitch. `describe()` reports
# `bay_pitch` 1.105263 because it converts that one field to simulation units
# while reporting every other field in layout; 0.63 layout and 1.105263
# simulation are `layout.BAY_PITCH` twice over.


static func shuffle_start(palette, contract: Dictionary) -> Node3D:
	var root := Node3D.new()
	root.name = "Start"
	_shuffle_pan(root, palette, contract)
	_shuffle_chamber(root, palette, contract)
	_shuffle_cone(root, palette, contract)
	_shuffle_chute(root, palette, contract)
	_shuffle_frame(root, palette, contract)
	var pan: Dictionary = contract["pan"]
	sign_panel(root, palette, "START", 4.6,
		Vector3(0.0, float(pan["floor"]) + 2.26, float(pan["back"]) - 0.52),
		"sign_face", "lit_white")
	return root


static func _apron_y(contract: Dictionary, z: float) -> float:
	## The pan and apron are ONE ramp, and this is its height at a station.
	##
	## Measured off the built collider rather than assumed: a downward ray at
	## the module's own x = 0 descends from -0.155 at z = -4.60 to -0.704 at
	## z = -2.40 at a constant 14 degrees, which is `apron_grade_deg`, and
	## passes through `pan.floor` = -0.32 at z = -3.94 - which is exactly where
	## the replay's eight marbles sit for the first four tenths of a second. So
	## `pan.floor` is the ramp's height at the bays rather than a flat deck.
	var pan: Dictionary = contract["pan"]
	var chamber: Dictionary = contract["chamber"]
	var rim: float = float(chamber["centre_z"]) - float(chamber["wall_radius"])
	var top: float = float(chamber["rim_floor"]) + float(pan["inlet_step"])
	var grade := tan(deg_to_rad(float(pan["apron_grade_deg"])))
	return top + (rim - z) * grade


static func _shuffle_pan(root: Node3D, palette, contract: Dictionary) -> void:
	## The eight bays: a tray on the apron's own slope, with seven fins.
	var pan: Dictionary = contract["pan"]
	var chamber: Dictionary = contract["chamber"]
	var bays: Array = contract["bay_x"]
	var half := float(pan["half"])
	var back := float(pan["back"])
	var front: float = float(chamber["centre_z"]) - float(chamber["wall_radius"]) + 0.02
	var samples := 24

	var path: Array = []
	var sections: Array = []
	var normals: Array = []
	var banks: Array = []
	for index in samples:
		var t := float(index) / float(samples - 1)
		var z := lerpf(back, front, t)
		path.append(Vector3(0.0, _apron_y(contract, z), z))
		var built := trough_section(half)
		sections.append(built[0])
		normals.append(built[1])
		banks.append(0.0)
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, sections, normals, banks),
		palette.get_material("pearl_shell"), "Pan"))

	var inner: Array = []
	var inner_normals: Array = []
	for index in samples:
		var built := floor_section(half - 0.05)
		inner.append(built[0])
		inner_normals.append(built[1])
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, inner, inner_normals, banks),
		palette.get_material("running_polished"), "PanFloor", false))

	for index in bays.size() - 1:
		var x: float = (float(bays[index]) + float(bays[index + 1])) * 0.5
		var lane: Array = []
		for step in samples:
			var centre: Vector3 = path[step]
			lane.append(Vector3(x, centre.y + 0.09, centre.z))
		root.add_child(Forms.mesh_node(Geometry.tube(lane, 0.055, 8),
			palette.get_material("pearl_lip_v2"), "Fin%d" % index, false))

	for side in [1.0, -1.0]:
		var suffix := "R" if side > 0.0 else "L"
		var rail: Array = []
		var line: Array = []
		for step in samples:
			var centre: Vector3 = path[step]
			rail.append(Vector3(side * (half + 0.16), centre.y + 0.36, centre.z))
			line.append(Vector3(side * (half + 0.21), centre.y + 0.04, centre.z))
		root.add_child(Forms.mesh_node(Geometry.tube(rail, 0.075, 10),
			palette.get_material("chrome"), "PanRail%s" % suffix, false))
		root.add_child(Forms.mesh_node(Geometry.tube(line, 0.05, 8),
			palette.get_material("lit_cyan_line_hero"), "PanLine%s" % suffix, false))


static func _shuffle_chamber(root: Node3D, palette, contract: Dictionary) -> void:
	## The mixing drum: an acrylic wall on a pearl kerb, open where the pan feeds.
	var chamber: Dictionary = contract["chamber"]
	var rotor: Dictionary = contract["rotor"]
	var radius := float(chamber["wall_radius"])
	var floor_y := float(chamber["rim_floor"])
	var rise := float(chamber["wall_rise"])
	var centre := Vector3(0.0, 0.0, float(chamber["centre_z"]))

	var gap := deg_to_rad(float(chamber["inlet_half_deg"]))
	var mouth := -PI * 0.5
	var wall := Node3D.new()
	wall.name = "ChamberWall"
	wall.position = centre + Vector3(0.0, floor_y, 0.0)
	root.add_child(wall)
	# Five rings rather than a solid cylinder: the drum has to be **seen into**
	# or the eight racers waiting in it are behind frosted acrylic, and the
	# first render of this put a wall between the camera and the whole field.
	for ring in 5:
		var y: float = rise * (float(ring) + 0.5) / 5.0
		var hoop := Forms.mesh_node(
			Forms.arc_hoop(radius, 0.05, mouth + gap, mouth + TAU - gap, 48, 8),
			palette.get_material("acrylic_guard"), "Hoop%d" % ring, false)
		hoop.position = Vector3(0.0, y, 0.0)
		wall.add_child(hoop)
	var kerb := Forms.mesh_node(
		Forms.arc_hoop(radius, 0.10, mouth + gap, mouth + TAU - gap, 48, 10),
		palette.get_material("pearl_lip_v2"), "Kerb", false)
	kerb.position = Vector3(0.0, 0.02, 0.0)
	wall.add_child(kerb)
	var crown := Forms.mesh_node(
		Forms.arc_hoop(radius, 0.07, mouth + gap, mouth + TAU - gap, 48, 10),
		palette.get_material("chrome"), "Crown", false)
	crown.position = Vector3(0.0, rise, 0.0)
	wall.add_child(crown)

	# **No hub and no post at marble height.** `ShuffleFloor.rest_radius` is
	# zero - the field rests anywhere on the disc, the chamber axis included -
	# so a drawn hub is a wall the physics has not got, and the first render of
	# this put a 1.01-radius graphite disc straight through four of the eight
	# waiting racers. The spindle therefore starts a marble's height clear of
	# the floor and hangs from the gantry above.
	var clear: float = float(rotor["height"]) + 0.12
	var post := Forms.mesh_node(
		Geometry.tube([centre + Vector3(0.0, floor_y + clear, 0.0),
			centre + Vector3(0.0, floor_y + rise + 1.05, 0.0)], 0.075, 12),
		palette.get_material("chrome"), "RotorPost", false)
	root.add_child(post)
	var collar := Forms.mesh_node(
		Geometry.rounded_disc(0.30, 0.14, 0.05, 24, 3),
		palette.get_material("graphite"), "RotorCollar", false)
	collar.position = centre + Vector3(0.0, floor_y + clear, 0.0)
	root.add_child(collar)
	var gantry := Forms.mesh_node(
		Forms.hoop(radius * 0.72, 0.06, 32, 8),
		palette.get_material("graphite"), "RotorGantry", false)
	gantry.position = centre + Vector3(0.0, floor_y + rise + 1.05, 0.0)
	root.add_child(gantry)
	for index in 3:
		var angle := TAU * float(index) / 3.0
		root.add_child(Forms.mesh_node(
			Geometry.tube([centre + Vector3(0.0, floor_y + rise + 1.05, 0.0),
				centre + Vector3(cos(angle) * radius * 0.72,
					floor_y + rise + 1.05, sin(angle) * radius * 0.72)],
				0.05, 8),
			palette.get_material("graphite"), "Spoke%d" % index, false))


static func _shuffle_cone(root: Node3D, palette, contract: Dictionary) -> void:
	## The catch cone under the trapdoor, and the guard round its rim.
	var cone: Dictionary = contract["cone"]
	var chamber: Dictionary = contract["chamber"]
	var rim := float(cone["rim"])
	var lip := float(cone["lip"])
	var outer := float(cone["half"])
	var throat := float(cone["throat"])
	var points: Array = [
		Vector2(throat, lip),
		Vector2(outer, rim),
		Vector2(outer + 0.14, rim + float(cone["rim_rise"])),
		Vector2(outer + 0.26, rim + float(cone["rim_rise"])),
		Vector2(outer + 0.26, rim - 0.34),
		Vector2(throat + 0.10, lip - 0.30),
	]
	var normals: Array = Geometry.profile_normals(points, true)
	var dish := Forms.mesh_node(Geometry.lathe(points, normals, 48),
		palette.get_material("pearl_shell"), "CatchCone")
	dish.position = Vector3(0.0, 0.0, float(chamber["centre_z"]))
	root.add_child(dish)

	var ring := Forms.mesh_node(
		Forms.hoop(outer + 0.26, 0.06, 48, 8),
		palette.get_material("lit_cyan_line_hero"), "ConeLine", false)
	ring.position = Vector3(0.0, rim + float(cone["rim_rise"]),
		float(chamber["centre_z"]))
	root.add_child(ring)


static func _shuffle_chute(root: Node3D, palette, contract: Dictionary) -> void:
	## The run-out to the first track run, at the physics' own grade.
	var chute: Dictionary = contract["chute"]
	var exit_local: Array = contract["exit_local"]
	var mouth := Vector3(0.0, float(chute["lip"]), float(chute["mouth_z"]))
	var landing := Vector3(float(exit_local[0]), float(exit_local[1]),
		float(exit_local[2]))
	var samples := 16
	var path: Array = []
	var sections: Array = []
	var normals: Array = []
	var banks: Array = []
	for index in samples:
		var t := float(index) / float(samples - 1)
		path.append(mouth.lerp(landing, t))
		var built := trough_section(float(chute["half"]))
		sections.append(built[0])
		normals.append(built[1])
		banks.append(0.0)
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, sections, normals, banks),
		palette.get_material("pearl_shell"), "Chute"))
	var inner: Array = []
	var inner_normals: Array = []
	for index in samples:
		var built := floor_section(float(chute["half"]) - 0.05)
		inner.append(built[0])
		inner_normals.append(built[1])
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, inner, inner_normals, banks),
		palette.get_material("running_polished"), "ChuteFloor", false))
	for side in [1.0, -1.0]:
		var line: Array = []
		for step in samples:
			var centre: Vector3 = path[step]
			line.append(Vector3(side * (float(chute["half"]) + 0.14),
				centre.y + 0.06, centre.z))
		root.add_child(Forms.mesh_node(Geometry.tube(line, 0.045, 8),
			palette.get_material("lit_cyan_line_hero"),
			"ChuteLine%s" % ("R" if side > 0.0 else "L"), false))


static func _shuffle_frame(root: Node3D, palette, contract: Dictionary) -> void:
	## What the drum stands on: four graphite legs and a collar.
	var chamber: Dictionary = contract["chamber"]
	var cone: Dictionary = contract["cone"]
	var centre_z := float(chamber["centre_z"])
	var radius: float = float(cone["half"]) + 0.20
	var top: float = float(cone["rim"]) - 0.30
	var foot: float = float(cone["lip"]) - 2.30
	for index in 4:
		var angle := TAU * (float(index) + 0.5) / 4.0
		var at := Vector3(cos(angle) * radius, 0.0, centre_z + sin(angle) * radius)
		var base := Vector3(at.x * 1.16, foot, centre_z + (at.z - centre_z) * 1.16)
		root.add_child(Forms.mesh_node(
			Geometry.tube([at + Vector3(0.0, top, 0.0), base], 0.105, 10),
			palette.get_material("graphite"), "Leg%d" % index, false))
	var collar := Forms.mesh_node(Forms.hoop(radius, 0.075, 40, 8),
		palette.get_material("chrome"), "Collar", false)
	collar.position = Vector3(0.0, top, centre_z)
	root.add_child(collar)


static func shuffle_start_parts(palette, contract: Dictionary,
		scale: float) -> Dictionary:
	## One box per kinematic part, keyed by its replay actuator name.
	##
	## Built at **simulation** size, because the caller parents them to the same
	## `render_scale` node the replay marbles hang from - one conversion in the
	## pipeline, on one node, exactly as `sloped_race_scene.gd` documents.
	var out: Dictionary = {}
	var parts: Dictionary = contract["parts"]
	var factor: float = 1.0 / maxf(scale, 1.0e-6)
	for name in parts:
		var entry: Dictionary = parts[name]
		var size: Array = entry["size"]
		var box := Vector3(float(size[0]), float(size[1]), float(size[2])) * factor
		var key := str(name)
		# The slats are the surface eight racers stand on for five of the six
		# seconds before the gun, so they are drawn in the polished metal the
		# channel uses rather than in acrylic - which read as a pale blur
		# against the catch cone below and made the floor look like no floor.
		var material := "graphite"
		if key.begins_with("panel"):
			material = "running_polished"
		elif key.begins_with("rotor"):
			material = "orange_machine"
		var node := Forms.mesh_node(
			Geometry.rounded_box(box, minf(box.y, box.x) * 0.22, 3),
			palette.get_material(material), "Part_%s" % key, false)
		out["start.%s" % key] = node
	return out


static func trough_section(half: float) -> Array:
	## An open tapering trough: a cradle floor, two low walls, real thickness.
	##
	## Returns `[points, normals]` for `V2Forms.banked_sweep`. Separate from
	## the signature channel's section on purpose: an apron is a *mouth*, it
	## has no keel hanging under it and no acrylic guard on its lip, and
	## reusing the channel profile for one is what gave the first start fan a
	## metre-deep white belly floating over its own pod.
	var wall := 0.15
	var points: Array = [Vector2(half + wall, 0.32),
		Vector2(half + wall, -0.44), Vector2(-half - wall, -0.44),
		Vector2(-half - wall, 0.32), Vector2(-half, 0.32)]
	for step in 9:
		var x: float = lerpf(-half, half, float(step) / 8.0)
		points.append(Vector2(x, _cradle(x, half)))
	points.append(Vector2(half, 0.32))
	points.append(points[0])
	var closed: Array = V2Forms.ensure_ccw(points)
	return [closed, V2Forms.section_normals(closed)]


static func floor_section(half: float) -> Array:
	## The polished insert that sits in a trough.
	var points: Array = []
	for step in 11:
		var x: float = lerpf(-half, half, float(step) / 10.0)
		points.append(Vector2(x, _cradle(x, half) + 0.02))
	for step in 11:
		var x: float = lerpf(half, -half, float(step) / 10.0)
		points.append(Vector2(x, _cradle(x, half) - 0.05))
	points.append(points[0])
	var closed: Array = V2Forms.ensure_ccw(points)
	return [closed, V2Forms.section_normals(closed)]


static func _cradle(x: float, half: float) -> float:
	## A shallow dish across the trough, deepest on the centreline.
	var t: float = clampf(absf(x) / maxf(half, 0.001), 0.0, 1.0)
	return -0.30 + 0.16 * t * t


# --- MIXER ----------------------------------------------------------------


static func mixer(palette) -> Node3D:
	## The order shuffler: two staggered pin rows behind an acrylic window.
	##
	## Subordinate on purpose. The brief's rule is that the fairness mechanism
	## must not be the largest object at the top of the course, and an open
	## Plinko deck the width of the start is exactly that. This is a housing
	## the width of the channel it sits on, with the mechanism visible through
	## a window rather than displayed on a board.
	var root := Node3D.new()
	root.name = "Mixer"

	var housing := Forms.mesh_node(
		Geometry.rounded_box(Vector3(3.10, 1.36, 2.30), 0.22, 4),
		palette.get_material("graphite"), "Housing")
	housing.position = Vector3(0.0, -0.28, 0.0)
	root.add_child(housing)

	var window := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.40, 0.92, 0.14), 0.06, 3),
		palette.get_material("acrylic_guard"), "Window", false)
	window.position = Vector3(0.0, -0.16, 1.14)
	root.add_child(window)

	for row in 2:
		var count := 5 - row
		for index in count:
			var span := (float(index) - float(count - 1) * 0.5) * 0.52
			var pin := Forms.mesh_node(
				Geometry.tube([Vector3(span, -0.62, -0.24 + float(row) * 0.48),
					Vector3(span, -0.06, -0.24 + float(row) * 0.48)],
					0.075, 10),
				palette.get_material("chrome"), "Pin%d_%d" % [row, index],
				false)
			root.add_child(pin)

	var crown := Forms.mesh_node(
		Geometry.rounded_box(Vector3(3.24, 0.14, 2.44), 0.06, 3),
		palette.get_material("neon_violet_hero"), "Crown", false)
	crown.position = Vector3(0.0, 0.46, 0.0)
	root.add_child(crown)

	for side in [1.0, -1.0]:
		var boss := Forms.mesh_node(
			Geometry.rounded_disc(0.24, 0.18, 0.06, 16, 3),
			palette.get_material("gold"),
			"Boss%s" % ("R" if side > 0.0 else "L"), false)
		boss.position = Vector3(side * 1.60, -0.18, 0.0)
		boss.rotation.z = PI * 0.5
		root.add_child(boss)
	return root


# --- OBSTACLE -------------------------------------------------------------


static func obstacle(palette) -> Node3D:
	## A spinner corridor: three paddle wheels turning across the channel.
	##
	## The one mechanical event on the course, and the only place a racer's
	## order can change for a reason the viewer can see. Built as an open
	## gantry the field runs *through* rather than a machine it falls into, so
	## nothing stops - which is the brief's rule for this section.
	##
	## Open is the operative word. The first build gave it two solid side rails
	## two and a half units tall, and from every camera that stands beside a
	## track those rails are the module: the three wheels turned behind a wall.
	## Corner posts and a top frame show the same structure and hide nothing.
	var root := Node3D.new()
	root.name = "Obstacle"

	var half := 1.78
	var reach := 2.55
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			var post := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.26, 2.10, 0.30), 0.10, 3),
				palette.get_material("graphite"),
				"Post%d%d" % [int(float(sx)), int(float(sz))])
			post.position = Vector3(float(sx) * half, 0.62, float(sz) * reach)
			root.add_child(post)

	for sx in [-1.0, 1.0]:
		var suffix := "R" if float(sx) > 0.0 else "L"
		# One slim rail per side rather than a structural beam. At full depth
		# the two side beams and the three cross beams together read as a flat
		# table lid over the corridor and the wheels turned underneath it.
		var beam := Forms.mesh_node(
			Geometry.tube([Vector3(float(sx) * half, 1.62, -reach),
				Vector3(float(sx) * half, 1.62, reach)], 0.09, 8),
			palette.get_material("graphite_soft"), "Beam%s" % suffix, false)
		root.add_child(beam)
		var strip := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.13, 0.13, reach * 2.0 - 0.10),
				0.05, 3),
			palette.get_material("lit_orange_line"), "Line%s" % suffix, false)
		strip.position = Vector3(float(sx) * (half + 0.16), 1.62, 0.0)
		root.add_child(strip)

		# A low amber guard along the channel, and the warning stripes on its
		# outer face. Low enough that a racer stays the tallest thing in the
		# corridor, which is the same rule the track's own guards follow.
		var guard := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.11, 0.62, reach * 2.0 - 0.20),
				0.04, 3),
			palette.get_material("acrylic_amber"), "Guard%s" % suffix, false)
		guard.position = Vector3(float(sx) * 1.40, 0.30, 0.0)
		root.add_child(guard)
		for index in 7:
			var chevron := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.07, 0.34, 0.26), 0.02, 2),
				palette.get_material("orange_machine" if index % 2 == 0
					else "graphite_deep"), "Chevron%s%d" % [suffix, index],
				false)
			chevron.position = Vector3(float(sx) * 1.50, -0.16,
				(float(index) - 3.0) * 0.66)
			root.add_child(chevron)

	for index in 3:
		var z := (float(index) - 1.0) * 1.62
		var cross := Forms.mesh_node(
			Geometry.rounded_box(Vector3(half * 2.0 + 0.24, 0.24, 0.34),
				0.09, 3),
			palette.get_material("graphite_soft"), "Cross%d" % index)
		cross.position = Vector3(0.0, 1.62, z)
		root.add_child(cross)

		var spinner := Node3D.new()
		spinner.name = "Spinner%d" % index
		spinner.position = Vector3(0.0, 1.46, z)
		spinner.set_meta("spin_phase", float(index) * 1.05)
		root.add_child(spinner)

		var shaft := Forms.mesh_node(
			Geometry.tube([Vector3(0.0, 0.0, 0.0), Vector3(0.0, -1.20, 0.0)],
				0.075, 10),
			palette.get_material("chrome"), "Shaft", false)
		spinner.add_child(shaft)
		var housing := Forms.mesh_node(
			Geometry.rounded_disc(0.30, 0.32, 0.09, 18, 3),
			palette.get_material("gold_dark"), "Head", false)
		housing.position = Vector3(0.0, 0.16, 0.0)
		spinner.add_child(housing)

		var wheel := Node3D.new()
		wheel.name = "Wheel"
		wheel.position = Vector3(0.0, -1.24, 0.0)
		spinner.add_child(wheel)
		var hub := Forms.mesh_node(
			Geometry.rounded_disc(0.26, 0.22, 0.07, 16, 3),
			palette.get_material("orange_deep"), "Hub", false)
		wheel.add_child(hub)
		for blade in 4:
			var pivot := Node3D.new()
			pivot.name = "Arm%d" % blade
			pivot.rotation.y = TAU * float(blade) / 4.0
			wheel.add_child(pivot)
			var arm := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.15, 0.78, 1.34), 0.06, 3),
				palette.get_material("orange_machine"), "Blade%d" % blade)
			arm.position = Vector3(0.0, -0.20, 0.72)
			pivot.add_child(arm)
			var tip := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.19, 0.16, 0.24), 0.06, 2),
				palette.get_material("gold"), "Tip%d" % blade, false)
			tip.position = Vector3(0.0, -0.54, 1.28)
			pivot.add_child(tip)

	# The drive: a machinery block on one side, where the shafts are geared.
	var drive := Forms.mesh_node(
		Geometry.rounded_box(Vector3(0.44, 0.52, reach * 1.4), 0.14, 3),
		palette.get_material("orange_machine"), "Drive")
	drive.position = Vector3(half + 0.30, 1.88, 0.0)
	root.add_child(drive)
	for index in 3:
		var gear := Forms.mesh_node(
			Geometry.rounded_disc(0.18, 0.12, 0.04, 14, 3),
			palette.get_material("gold"), "Gear%d" % index, false)
		gear.position = Vector3(half + 0.58, 1.88, (float(index) - 1.0) * 1.62)
		gear.rotation.z = PI * 0.5
		root.add_child(gear)
	return root


# --- SHUFFLE --------------------------------------------------------------


static func shuffle(palette) -> Node3D:
	## One paddle wheel on the launch, thirty-two samples down.
	##
	## The physics gained this in V1.1 and the render has to show it, because a
	## marble bouncing off nothing is a worse defect than an extra part. It is
	## the same mechanism as the obstacle's wheels - four blades on a shaft,
	## turning about the channel's up axis - built once instead of three times,
	## and dressed in the start's chrome and pearl rather than the obstacle's
	## amber, because it is not the race's set piece and should not read as one.
	##
	## No gantry and no guards. The obstacle needs a frame because it spans a
	## corridor the field runs through at 40 wu/s; this stands over a channel
	## the field is still accelerating down, and a frame here would read as a
	## second obstacle at the top of the course.
	##
	## `docs/sloped_race_v11.md` has what it does. The short version: at the
	## launch entry the same wheel jammed a fifth of the field, and thirty-two
	## samples down it takes the finish rate from 0.906 to 0.969.
	var root := Node3D.new()
	root.name = "Shuffle"

	var spinner := Node3D.new()
	spinner.name = "Spinner0"
	spinner.position = Vector3(0.0, 1.34, 0.0)
	spinner.set_meta("spin_phase", 0.0)
	root.add_child(spinner)

	var mast := Forms.mesh_node(
		Geometry.tube([Vector3(0.0, 0.0, 0.0), Vector3(0.0, -1.14, 0.0)],
			0.065, 10),
		palette.get_material("chrome"), "Shaft", false)
	spinner.add_child(mast)
	var head := Forms.mesh_node(
		Geometry.rounded_disc(0.26, 0.28, 0.08, 18, 3),
		palette.get_material("gold_dark"), "Head", false)
	head.position = Vector3(0.0, 0.14, 0.0)
	spinner.add_child(head)

	var wheel := Node3D.new()
	wheel.name = "Wheel"
	wheel.position = Vector3(0.0, -1.18, 0.0)
	spinner.add_child(wheel)
	var hub := Forms.mesh_node(
		Geometry.rounded_disc(0.22, 0.19, 0.06, 16, 3),
		palette.get_material("chrome"), "Hub", false)
	wheel.add_child(hub)
	for blade in 4:
		var pivot := Node3D.new()
		pivot.name = "Arm%d" % blade
		pivot.rotation.y = TAU * float(blade) / 4.0
		wheel.add_child(pivot)
		var arm := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.13, 0.70, 1.34), 0.05, 3),
			palette.get_material("pearl_shade"), "Blade%d" % blade)
		arm.position = Vector3(0.0, -0.18, 0.72)
		pivot.add_child(arm)
		var tip := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.17, 0.14, 0.22), 0.05, 2),
			palette.get_material("gold"), "Tip%d" % blade, false)
		tip.position = Vector3(0.0, -0.48, 1.28)
		pivot.add_child(tip)

	# A collar where the shaft is driven, so the wheel stands on something
	# rather than hanging over the channel from nothing.
	var collar := Forms.mesh_node(
		Geometry.rounded_disc(0.34, 0.30, 0.10, 16, 3),
		palette.get_material("graphite"), "Collar", false)
	collar.position = Vector3(0.0, 1.50, 0.0)
	root.add_child(collar)
	return root


# --- SPLIT ----------------------------------------------------------------


static func split(palette) -> Node3D:
	## The choice: a wedge between two coloured portals.
	##
	## Read at phone size a split has to be a *decision*, and two channels that
	## differ only in the colour of their edge light are not one. So each route
	## gets a portal frame in its own body colour standing over its mouth, an
	## arrow on the outside of it, and the wedge between them carries a chrome
	## nose so the point of separation catches a highlight and the eye lands
	## exactly where the race divides.
	var root := Node3D.new()
	root.name = "Split"

	var wedge := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.05, 1.20, 3.40), 0.26, 4),
		palette.get_material("graphite"), "Wedge")
	wedge.position = Vector3(0.0, -0.05, 1.30)
	root.add_child(wedge)
	root.add_child(Forms.mesh_node(
		Geometry.tube([Vector3(0.0, 0.40, -0.55), Vector3(0.0, 0.40, 0.55)],
			0.15, 12), palette.get_material("chrome"), "Nose", false))
	var cap := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.16, 0.14, 3.30), 0.06, 3),
		palette.get_material("lit_white"), "WedgeLine", false)
	cap.position = Vector3(0.0, 0.56, 1.34)
	root.add_child(cap)

	for side in [-1.0, 1.0]:
		var cool: bool = float(side) < 0.0
		var suffix := "Blue" if cool else "Orange"
		var body := "blue_machine" if cool else "orange_machine"
		var lit := "neon_blue" if cool else "lit_orange_line"
		var lean: float = float(side) * deg_to_rad(20.0)

		var portal := Node3D.new()
		portal.name = "Portal%s" % suffix
		portal.position = Vector3(side * 2.05, 0.0, 2.30)
		portal.rotation.y = lean
		root.add_child(portal)

		for post in [-1.0, 1.0]:
			var leg := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.46, 2.30, 0.56), 0.18, 3),
				palette.get_material(body),
				"Leg%d" % int(float(post)))
			leg.position = Vector3(float(post) * 1.36, 0.80, 0.0)
			portal.add_child(leg)
		var lintel := Forms.mesh_node(
			Geometry.rounded_box(Vector3(3.30, 0.62, 0.64), 0.20, 3),
			palette.get_material(body), "Lintel")
		lintel.position = Vector3(0.0, 2.22, 0.0)
		portal.add_child(lintel)
		var strip := Forms.mesh_node(
			Geometry.rounded_box(Vector3(2.80, 0.18, 0.18), 0.07, 3),
			palette.get_material(lit), "Strip", false)
		strip.position = Vector3(0.0, 1.86, 0.34)
		portal.add_child(strip)
		# The route's own name plate, on the lintel and facing downhill.
		var plate := Forms.mesh_node(
			Geometry.rounded_box(Vector3(2.20, 0.40, 0.10), 0.06, 3),
			palette.get_material(lit), "Plate", false)
		plate.position = Vector3(0.0, 2.22, 0.34)
		portal.add_child(plate)
		var apron := Forms.mesh_node(
			Geometry.rounded_box(Vector3(2.20, 0.26, 1.60), 0.12, 3),
			palette.get_material(body), "Apron", false)
		apron.position = Vector3(0.0, -0.56, 0.10)
		portal.add_child(apron)

	var gantry := Forms.mesh_node(
		Geometry.rounded_box(Vector3(6.60, 0.34, 0.50), 0.14, 3),
		palette.get_material("graphite_soft"), "Gantry")
	gantry.position = Vector3(0.0, 2.62, 0.10)
	root.add_child(gantry)
	for side in [1.0, -1.0]:
		var post := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.34, 2.70, 0.44), 0.13, 3),
			palette.get_material("graphite"),
			"GantryPost%s" % ("R" if side > 0.0 else "L"))
		post.position = Vector3(side * 3.10, 1.30, 0.10)
		root.add_child(post)
	return root


# --- MERGE ----------------------------------------------------------------


static func merge(palette, blue_local: Vector3, orange_local: Vector3,
		exit_local: Vector3) -> Node3D:
	## Where the two routes compress back into one channel.
	##
	## Small on purpose. The first build gave it an eight-unit warm pan bridging
	## inlets three units either side of the centreline, because the branches
	## were still that far apart when they ended - which made the junction the
	## widest object on the lower half of the course and hid the moment it was
	## supposed to stage. The branches now converge on their own and this is
	## only the throat they converge into: a graphite housing, a gold collar
	## round its mouth, and one lip in each route's colour so the last thing a
	## viewer sees before the sprint is which side each racer came in on.
	var root := Node3D.new()
	root.name = "Merge"

	var spread: float = maxf(absf(blue_local.x - orange_local.x), 1.6)
	var housing := Forms.mesh_node(
		Geometry.rounded_box(Vector3(spread + 1.90, 1.30, 2.40), 0.30, 4),
		palette.get_material("graphite"), "Housing")
	housing.position = Vector3(0.0, -0.72, 0.10)
	root.add_child(housing)

	var deck := Forms.mesh_node(
		Geometry.rounded_box(Vector3(spread + 1.40, 0.26, 1.90), 0.12, 3),
		palette.get_material("pearl_warm"), "Deck", false)
	deck.position = Vector3(0.0, -0.12, 0.10)
	root.add_child(deck)

	for entry in [[blue_local, "blue_machine", "neon_blue", "Blue"],
			[orange_local, "orange_machine", "lit_orange_line", "Orange"]]:
		var at: Vector3 = entry[0]
		var lip := Forms.mesh_node(
			Geometry.rounded_box(Vector3(1.30, 0.42, 0.90), 0.16, 3),
			palette.get_material(str(entry[1])), "Inlet%s" % str(entry[3]),
			false)
		lip.position = Vector3(at.x * 0.86, 0.02, at.z + 0.28)
		root.add_child(lip)
		var line := Forms.mesh_node(
			Geometry.rounded_box(Vector3(1.36, 0.12, 0.14), 0.05, 3),
			palette.get_material(str(entry[2])), "Line%s" % str(entry[3]),
			false)
		line.position = Vector3(at.x * 0.86, 0.24, at.z + 0.28)
		root.add_child(line)

	var collar := Forms.mesh_node(
		Geometry.rounded_disc(0.98, 0.30, 0.10, 26, 3),
		palette.get_material("gold"), "Collar", false)
	collar.position = exit_local + Vector3(0.0, -0.02, -0.16)
	collar.rotation.x = PI * 0.5
	root.add_child(collar)

	for side in [1.0, -1.0]:
		var wing := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.30, 1.10, 0.44), 0.12, 3),
			palette.get_material("graphite_soft"),
			"Wing%s" % ("R" if float(side) > 0.0 else "L"))
		wing.position = Vector3(float(side) * (spread * 0.5 + 0.80), 0.24,
			0.10)
		root.add_child(wing)
	return root


# --- shared parts ---------------------------------------------------------


static func sign_panel(root: Node3D, palette, text: String, width: float,
		at: Vector3, face_key: String, letter_key: String,
		arms := true) -> void:
	## A framed, lit sign carrying real 3D text.
	##
	## Real letters rather than a bright rectangle: a blank lit panel is a
	## lamp, and a lamp gives a module no identity at all. Kept from the tower
	## build unchanged, because it was the part of that start that worked.
	var pivot := Node3D.new()
	pivot.name = "Sign%s" % text.capitalize()
	pivot.position = at
	pivot.rotation.x = deg_to_rad(9.0)
	root.add_child(pivot)

	pivot.add_child(Forms.mesh_node(
		Geometry.rounded_box(Vector3(width, width * 0.235, 0.28), 0.13, 4),
		palette.get_material("graphite_soft"), "Frame"))
	# The face and the letters sit on the +Z side. Every camera on this course
	# stands downhill of what it is looking at, so a sign that faces uphill is
	# a dark rectangle in every frame it appears in - which is exactly what
	# the first build of the start shipped.
	var face := Forms.mesh_node(
		Geometry.rounded_box(Vector3(width * 0.89, width * 0.142, 0.10),
			0.055, 3),
		palette.get_material(face_key), "Face", false)
	face.position = Vector3(0.0, 0.0, 0.13)
	pivot.add_child(face)

	var letters := TextMesh.new()
	letters.text = text
	letters.font_size = 96
	letters.pixel_size = width * 0.00205
	letters.depth = 0.05
	letters.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	letters.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var word := Forms.mesh_node(letters, palette.get_material(letter_key),
		"Letters", false)
	word.position = Vector3(0.0, 0.0, 0.21)
	pivot.add_child(word)

	for side in [1.0, -1.0]:
		var boss := Forms.mesh_node(
			Geometry.rounded_disc(0.16, 0.13, 0.05, 16, 3),
			palette.get_material("gold"),
			"Boss%s" % ("R" if side > 0.0 else "L"), false)
		boss.position = Vector3(side * (width * 0.47), 0.0, 0.10)
		boss.rotation.x = PI * 0.5
		pivot.add_child(boss)

	# The shoulders that carry the frame off the module's own body. They run
	# from deck level to the frame, not from mid-air: a sign on stilts that
	# start half way up is the tell that it was placed rather than built.
	if not arms:
		return
	for side in [1.0, -1.0]:
		var arm := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.30, at.y * 0.92, 0.40), 0.13, 3),
			palette.get_material("graphite"),
			"Arm%s" % ("R" if side > 0.0 else "L"))
		arm.position = Vector3(side * width * 0.38, at.y * 0.46, at.z - 0.04)
		root.add_child(arm)


static func _skirt(root: Node3D, palette, width: float, depth: float,
		top: float, drop: float, at_z := 0.0) -> void:
	## The dark chassis under a module: what separates it from its ground.
	var skirt := Forms.mesh_node(
		Geometry.rounded_box(Vector3(width, drop, depth), 0.24, 3),
		palette.get_material("graphite_deep"), "Skirt")
	skirt.position = Vector3(0.0, top - drop * 0.5, at_z)
	root.add_child(skirt)
	var band := Forms.mesh_node(
		Geometry.rounded_box(Vector3(width + 0.10, 0.10, depth + 0.10),
			0.05, 3),
		palette.get_material("lit_gold_wash"), "Band", false)
	band.position = Vector3(0.0, top - 0.24, at_z)
	root.add_child(band)
	var bolts := Node3D.new()
	bolts.name = "SkirtBolts"
	bolts.position = Vector3(0.0, 0.0, at_z)
	root.add_child(bolts)
	Forms.bolt_ring(bolts, palette.get_material("gold"), 12,
		minf(width, depth) * 0.46, top - 0.62, 0.09, 0.08)
