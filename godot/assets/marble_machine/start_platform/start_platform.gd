extends RefCounted

## The start gate: eight marbles held in eight bays under an acrylic canopy.
##
## Deliberately not a rectangular slab with rails, which is what the brief
## rules out and what every earlier prototype produced. A slab has one
## silhouette - a horizontal line - and the concept's start platform has four
## stacked ones: the sign floating above, the canopy arch, the bay deck, and
## the dark chassis hanging below with its machinery visible. Reading that as
## four bands from top to bottom is what makes it a module.
##
## ## The bays are the design
##
## The single strongest idea in the reference's start platform is that each
## racer has its *own* place. Eight fins across a recessed deck turn one
## surface into eight, give the module a repeating rhythm at exactly the
## medium scale that was missing, and place the marbles in a readable row
## instead of a heap. The fins are moulded pearl with a warm tip, so the row
## also carries the warm note across the coolest zone of the machine.
##
## Local origin is the top face of the bay deck, centred on the run of bays.
## `marble_slots()` reports where the racers sit in that frame.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")

const BAYS := 8
const BAY_PITCH := 0.52
const BAY_DEPTH := 1.15
const DECK_WIDTH := BAYS * BAY_PITCH + 0.55
const MARBLE_RADIUS := 0.21


static func marble_slots() -> Array:
	## One resting position per bay, in this module's local frame.
	var slots: Array = []
	for index in BAYS:
		var x := (float(index) - float(BAYS - 1) * 0.5) * BAY_PITCH
		slots.append(Vector3(x, MARBLE_RADIUS + 0.03, 0.10))
	return slots


static func exit_local() -> Vector3:
	## Where the released field leaves the module, at the gate lip.
	return Vector3(0.0, -0.10, BAY_DEPTH * 0.5 + 0.28)


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "StartPlatform"

	_chassis(root, palette)
	_shell(root, palette)
	_bays(root, palette)
	_gate(root, palette)
	_canopy(root, palette)
	_sign(root, palette)
	_machinery(root, palette)

	return root


# --- structure ------------------------------------------------------------

static func _chassis(root: Node3D, palette) -> void:
	## The dark underside. Deeper than the shell it carries, and set back, so
	## the module has an overhang and therefore a shadow line under it.
	var body := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(DECK_WIDTH - 0.42, 0.62, BAY_DEPTH + 0.30), 0.16, 4),
		palette.get_material("graphite_deep"), "Chassis")
	body.position = Vector3(0.0, -0.52, -0.06)
	root.add_child(body)

	var keel := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(DECK_WIDTH - 1.30, 0.34, BAY_DEPTH - 0.20), 0.10, 3),
		palette.get_material("graphite"), "Keel")
	keel.position = Vector3(0.0, -0.92, -0.06)
	root.add_child(keel)

	# Four legs down to whatever carries the module. Visible support was on
	# the brief's list and it is also the only thing that stops a platform
	# looking pasted into the air.
	var leg := Geometry.rounded_box(Vector3(0.17, 1.05, 0.17), 0.055, 3)
	for index in 4:
		var x: float = (DECK_WIDTH * 0.5 - 0.62) * (1.0 if index % 2 == 0 else -1.0)
		var z: float = (BAY_DEPTH * 0.5 - 0.10) * (1.0 if index < 2 else -1.0)
		var post := Forms.mesh_node(leg, palette.get_material("graphite"),
			"Leg%d" % index)
		post.position = Vector3(x, -1.32, z)
		root.add_child(post)

		var foot := Forms.mesh_node(Forms.collar(0.16, 0.10),
			palette.get_material("gold"), "LegCollar%d" % index, false)
		foot.position = Vector3(x, -0.86, z)
		root.add_child(foot)


static func _shell(root: Node3D, palette) -> void:
	## The pearl body, with a recessed bay deck cut into its top.
	var shell := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(DECK_WIDTH, 0.46, BAY_DEPTH + 0.62), 0.17, 4),
		palette.get_material("pearl_shell"), "Shell")
	shell.position = Vector3(0.0, -0.24, 0.0)
	root.add_child(shell)

	var deck := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(DECK_WIDTH - 0.46, 0.14, BAY_DEPTH), 0.05, 3),
		palette.get_material("pearl_track"), "BayDeck")
	deck.position = Vector3(0.0, -0.05, 0.0)
	root.add_child(deck)

	# The cyan edge light, run in the shadow line between shell and chassis.
	for side in 2:
		var z: float = (BAY_DEPTH * 0.5 + 0.31) * (1.0 if side == 0 else -1.0)
		var strip := Forms.mesh_node(
			Geometry.rounded_box(Vector3(DECK_WIDTH - 0.62, 0.055, 0.035),
				0.016, 2),
			palette.get_material("lit_cyan"), "EdgeLight%d" % side, false)
		strip.position = Vector3(0.0, -0.44, z)
		root.add_child(strip)

	var trim := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(DECK_WIDTH + 0.05, 0.07, BAY_DEPTH + 0.67), 0.025, 3),
		palette.get_material("gold"), "ShellTrim", false)
	trim.position = Vector3(0.0, -0.46, 0.0)
	root.add_child(trim)


# --- bays -----------------------------------------------------------------

static func _bays(root: Node3D, palette) -> void:
	## Nine fins making eight lanes, each with a warm tip.
	var fin := Geometry.rounded_box(Vector3(0.075, 0.30, BAY_DEPTH - 0.06),
		0.03, 3)
	var tip := Geometry.rounded_box(Vector3(0.09, 0.055, 0.16), 0.02, 2)
	for index in BAYS + 1:
		var x := (float(index) - float(BAYS) * 0.5) * BAY_PITCH
		var blade := Forms.mesh_node(fin, palette.get_material("pearl_lip"),
			"Fin%d" % index)
		blade.position = Vector3(x, 0.13, 0.0)
		root.add_child(blade)

		var cap := Forms.mesh_node(tip, palette.get_material("gold"),
			"FinTip%d" % index, false)
		cap.position = Vector3(x, 0.28, BAY_DEPTH * 0.5 - 0.12)
		root.add_child(cap)

	# A lit strip down the floor of each lane. It is what puts a highlight
	# under the marbles from below, and it is why the row reads at distance.
	var lane := Geometry.rounded_box(
		Vector3(BAY_PITCH - 0.20, 0.02, BAY_DEPTH - 0.24), 0.008, 2)
	for index in BAYS:
		var x := (float(index) - float(BAYS - 1) * 0.5) * BAY_PITCH
		var lit := Forms.mesh_node(lane, palette.get_material("lit_cyan_soft"),
			"LaneLight%d" % index, false)
		lit.position = Vector3(x, 0.025, 0.0)
		root.add_child(lit)


static func _gate(root: Node3D, palette) -> void:
	## The release bar, dropped across the front of every lane at once.
	var bar := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH - 0.40, 0.14, 0.13), 0.05, 3),
		palette.get_material("gold"), "GateBar")
	bar.position = Vector3(0.0, 0.20, BAY_DEPTH * 0.5 + 0.02)
	root.add_child(bar)

	for side in 2:
		var x: float = (DECK_WIDTH * 0.5 - 0.20) * (1.0 if side == 0 else -1.0)
		var pillar := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.17, 0.50, 0.20), 0.06, 3),
			palette.get_material("silver"), "GatePillar%d" % side)
		pillar.position = Vector3(x, 0.20, BAY_DEPTH * 0.5 + 0.02)
		root.add_child(pillar)

		var motor := Forms.mesh_node(
			Geometry.rounded_disc(0.13, 0.16, 0.05, 20, 3),
			palette.get_material("orange_machine"), "GateMotor%d" % side, false)
		motor.position = Vector3(x, 0.34, BAY_DEPTH * 0.5 + 0.14)
		motor.rotation.z = PI * 0.5
		root.add_child(motor)

	# The lip the field runs out over: a short pearl apron with a silver edge.
	var apron := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH - 0.60, 0.10, 0.46), 0.04, 3),
		palette.get_material("pearl_track"), "GateApron")
	apron.position = Vector3(0.0, -0.06, BAY_DEPTH * 0.5 + 0.28)
	apron.rotation.x = 0.20
	root.add_child(apron)


static func _canopy(root: Node3D, palette) -> void:
	## A clear cover arched over the bays on two silver ribs.
	##
	## Curved rather than flat: a flat pane over a row of spheres reads as a
	## lid on a box, and an arch reads as a display case. The difference is
	## the whole "collectible" note the brief is asking for.
	var span := DECK_WIDTH * 0.5 - 0.10
	var controls: Array = [
		Vector3(-span, 0.30, 0.0),
		Vector3(-span * 0.55, 0.54, 0.0),
		Vector3(0.0, 0.60, 0.0),
		Vector3(span * 0.55, 0.54, 0.0),
		Vector3(span, 0.30, 0.0),
	]
	var arch := Forms.smooth_path(controls, 10)

	var section: Array = Geometry.beam_section(BAY_DEPTH * 0.5 + 0.04, 0.04, 0.015, 3)
	var pane := Forms.mesh_node(
		Geometry.sweep(arch, section[0], section[1], true),
		palette.get_material("acrylic_clear"), "Canopy", false)
	root.add_child(pane)

	for side in 2:
		var z: float = (BAY_DEPTH * 0.5 + 0.03) * (1.0 if side == 0 else -1.0)
		var rib_path: Array = []
		for point in arch:
			rib_path.append(Vector3(point.x, point.y, z))
		root.add_child(Forms.mesh_node(
			Geometry.tube(rib_path, 0.045, 8),
			palette.get_material("silver"), "CanopyRib%d" % side, false))


static func _sign(root: Node3D, palette) -> void:
	## START, lit, on two posts above the canopy.
	var height := 1.42
	for side in 2:
		var x: float = (DECK_WIDTH * 0.5 - 0.26) * (1.0 if side == 0 else -1.0)
		var post := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.11, height, 0.11), 0.04, 3),
			palette.get_material("graphite"), "SignPost%d" % side)
		post.position = Vector3(x, height * 0.5 + 0.05, -0.05)
		root.add_child(post)

	var frame := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH - 0.42, 0.56, 0.20), 0.08, 4),
		palette.get_material("graphite"), "SignFrame")
	frame.position = Vector3(0.0, height + 0.10, -0.05)
	root.add_child(frame)

	var face := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH - 0.70, 0.36, 0.05), 0.05, 3),
		palette.get_material("lit_sign"), "SignFace", false)
	face.position = Vector3(0.0, height + 0.10, 0.06)
	root.add_child(face)

	var bezel := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH - 0.36, 0.10, 0.24), 0.035, 3),
		palette.get_material("gold"), "SignBezel", false)
	bezel.position = Vector3(0.0, height + 0.40, -0.05)
	root.add_child(bezel)

	# Two lamps raking the sign face, which is what a real product shot does
	# and what stops the sign reading as a flat emissive rectangle.
	for side in 2:
		var x: float = (DECK_WIDTH * 0.5 - 0.60) * (1.0 if side == 0 else -1.0)
		var lamp := Forms.mesh_node(
			Geometry.rounded_disc(0.075, 0.10, 0.03, 16, 2),
			palette.get_material("chrome"), "SignLamp%d" % side, false)
		lamp.position = Vector3(x, height + 0.46, 0.16)
		lamp.rotation.x = 0.6
		root.add_child(lamp)


static func _machinery(root: Node3D, palette) -> void:
	## The warm parts: a gearbox each end and a rack under the front lip.
	for side in 2:
		var x: float = (DECK_WIDTH * 0.5 + 0.02) * (1.0 if side == 0 else -1.0)
		var case := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.34, 0.40, 0.62), 0.10, 3),
			palette.get_material("graphite_soft"), "Gearbox%d" % side)
		case.position = Vector3(x, -0.30, -0.10)
		root.add_child(case)

		var wheel := Forms.mesh_node(
			Geometry.rounded_disc(0.17, 0.11, 0.04, 20, 3),
			palette.get_material("orange_machine"), "GearWheel%d" % side, false)
		wheel.position = Vector3(x + (0.16 if side == 0 else -0.16), -0.30, -0.10)
		wheel.rotation.z = PI * 0.5
		root.add_child(wheel)

		var boss := Forms.mesh_node(
			Geometry.rounded_disc(0.06, 0.14, 0.02, 12, 2),
			palette.get_material("gold"), "GearBoss%d" % side, false)
		boss.position = Vector3(x + (0.22 if side == 0 else -0.22), -0.30, -0.10)
		boss.rotation.z = PI * 0.5
		root.add_child(boss)

	var rack := Node3D.new()
	rack.name = "FrontRack"
	rack.position = Vector3(0.0, -0.78, BAY_DEPTH * 0.5 - 0.05)
	root.add_child(rack)
	Forms.equipment_rack(rack, palette.get_material("graphite"),
		palette.get_material("gold"), palette.get_material("lit_cyan_soft"),
		2, DECK_WIDTH - 1.4)
