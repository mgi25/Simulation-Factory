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

	_fairings(root, palette)


static func _fairings(root: Node3D, palette) -> void:
	## The shoulders, the hood and the nose blade.
	##
	## What the module was short of was a silhouette. Four stacked bands read
	## as four bands; they do not read as a shape, and against a dark backdrop
	## the outline is most of what a viewer gets. So the shell now flares into
	## a rounded shoulder at each end, a raked hood closes the back of the bays
	## and carries the eye up to the sign, and a gold blade runs along the nose
	## where the field leaves. None of them touches a bay, a slot or the exit
	## lip - they are the parts that are only ever seen from outside.
	for side in 2:
		var x: float = (DECK_WIDTH * 0.5 + 0.10) * (1.0 if side == 0 else -1.0)
		var shoulder := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(0.46, 0.72, BAY_DEPTH + 0.34), 0.21, 4),
			palette.get_material("pearl_shell"), "Shoulder%d" % side)
		shoulder.position = Vector3(x, -0.20, -0.04)
		root.add_child(shoulder)

		var band := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(0.50, 0.09, BAY_DEPTH + 0.38), 0.03, 3),
			palette.get_material("gold"), "ShoulderBand%d" % side, false)
		band.position = Vector3(x, -0.44, -0.04)
		root.add_child(band)

		var vent := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.28, 0.30, 0.06), 0.02, 2),
			palette.get_material("lit_cyan_soft"), "ShoulderVent%d" % side,
			false)
		vent.position = Vector3(x, -0.12, BAY_DEPTH * 0.5 + 0.14)
		root.add_child(vent)

	# The hood: a raked plate over the back of the bays, on two ribs. It is
	# what turns the module's profile from a slab into a wedge.
	var hood := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(DECK_WIDTH - 0.30, 0.11, 0.62), 0.05, 3),
		palette.get_material("pearl_shade"), "Hood")
	hood.position = Vector3(0.0, 0.40, -BAY_DEPTH * 0.5 - 0.10)
	hood.rotation.x = -0.62
	root.add_child(hood)

	var hood_lip := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(DECK_WIDTH - 0.24, 0.06, 0.10), 0.025, 2),
		palette.get_material("gold"), "HoodLip", false)
	hood_lip.position = Vector3(0.0, 0.62, -BAY_DEPTH * 0.5 - 0.02)
	root.add_child(hood_lip)

	for side in 2:
		var x: float = (DECK_WIDTH * 0.5 - 0.34) * (1.0 if side == 0 else -1.0)
		var rib := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.09, 0.52, 0.11), 0.03, 3),
			palette.get_material("silver_deep"), "HoodRib%d" % side)
		rib.position = Vector3(x, 0.28, -BAY_DEPTH * 0.5 - 0.16)
		rib.rotation.x = -0.28
		root.add_child(rib)

	# The nose blade, under the exit lip and clear of it.
	var blade := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(DECK_WIDTH - 0.34, 0.09, 0.30), 0.035, 3),
		palette.get_material("gold"), "NoseBlade", false)
	blade.position = Vector3(0.0, -0.34, BAY_DEPTH * 0.5 + 0.40)
	blade.rotation.x = 0.24
	root.add_child(blade)

	var under := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(DECK_WIDTH - 0.62, 0.04, 0.05), 0.015, 2),
		palette.get_material("lit_cyan"), "NoseLight", false)
	under.position = Vector3(0.0, -0.42, BAY_DEPTH * 0.5 + 0.34)
	root.add_child(under)


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

	_readiness(root, palette)


static func _readiness(root: Node3D, palette) -> void:
	## Whether the gate is armed, said in hardware.
	##
	## A start gate that gives no signal is a bar. The module now carries the
	## state a start line actually has: one lamp per lane along the release
	## bar, and a stack of three discs on each pillar with the bottom one lit -
	## armed, not away. It is the one place in this machine where a light
	## means something rather than decorating something, and at hero distance
	## the row of eight is also the medium-scale rhythm the front of the
	## module was missing.
	var lamp := Geometry.rounded_disc(0.045, 0.05, 0.018, 12, 2)
	for index in BAYS:
		var x := (float(index) - float(BAYS - 1) * 0.5) * BAY_PITCH
		var pip := Forms.mesh_node(lamp, palette.get_material("lit_gold"),
			"LaneReady%d" % index, false)
		pip.position = Vector3(x, 0.27, BAY_DEPTH * 0.5 + 0.02)
		pip.rotation.x = PI * 0.5
		root.add_child(pip)

	var disc := Geometry.rounded_disc(0.058, 0.06, 0.02, 14, 2)
	for side in 2:
		var x: float = (DECK_WIDTH * 0.5 - 0.20) * (1.0 if side == 0 else -1.0)
		var stack := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.17, 0.42, 0.13), 0.05, 3),
			palette.get_material("graphite_deep"), "SignalStack%d" % side)
		stack.position = Vector3(x, 0.62, BAY_DEPTH * 0.5 + 0.02)
		root.add_child(stack)

		for step in 3:
			# Dark, dark, lit: the machine is holding, and the reading only
			# works because the two above the live one are unlit stock.
			var key := "lit_gold" if step == 2 else "graphite_soft"
			var light := Forms.mesh_node(disc, palette.get_material(key),
				"Signal%d_%d" % [side, step], false)
			light.position = Vector3(x, 0.76 - 0.14 * float(step),
				BAY_DEPTH * 0.5 + 0.08)
			light.rotation.x = PI * 0.5
			root.add_child(light)


static func _canopy(root: Node3D, palette) -> void:
	## A clear cover arched over the bays on two silver ribs.
	##
	## Curved rather than flat: a flat pane over a row of spheres reads as a
	## lid on a box, and an arch reads as a display case. The difference is
	## the whole "collectible" note the brief is asking for.
	# The arch clears the racers. It used to spring from 0.30, and the scene
	# draws its field at the simulation's radius rather than this module's, so
	# the pane cut the two outer marbles in half - a display case with the
	# exhibits through the glass. Springing from 0.52 the whole row passes
	# under it at any radius the race is likely to want.
	var span := DECK_WIDTH * 0.5 - 0.10
	var controls: Array = [
		Vector3(-span, 0.52, 0.0),
		Vector3(-span * 0.55, 0.74, 0.0),
		Vector3(0.0, 0.80, 0.0),
		Vector3(span * 0.55, 0.74, 0.0),
		Vector3(span, 0.52, 0.0),
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
	## START, and it says so.
	##
	## The old sign was a lit rectangle, and a lit rectangle at the top of a
	## machine is a placeholder for a sign rather than one. It made this the
	## weakest of the four modules in the hero frame by a distance: everything
	## else in the picture is a *part*, and the one element the eye goes to
	## first was a blank panel.
	##
	## So: a dark hood, a recessed face two shades under everything around it,
	## and the word standing proud of that face in lit stock, extruded far
	## enough that the key catches the top edge of every stroke. The value
	## order is what makes it read at phone size - dark surround, darker
	## recess, bright letters - and it survives being three centimetres tall
	## because it is a shape and not a texture.
	var height := 1.42
	var board := DECK_WIDTH - 0.42
	var y := height + 0.14

	for side in 2:
		var x: float = (DECK_WIDTH * 0.5 - 0.26) * (1.0 if side == 0 else -1.0)
		var post := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.13, height, 0.13), 0.045, 3),
			palette.get_material("graphite"), "SignPost%d" % side)
		post.position = Vector3(x, height * 0.5 + 0.05, -0.05)
		root.add_child(post)

		# A stay back to the canopy rib, so the sign is braced rather than
		# balanced. The posts alone read as two sticks under a board.
		root.add_child(Forms.mesh_node(
			Forms.brace(Vector3(x, height * 0.30, -0.05),
				Vector3(x * 0.82, 0.62, -BAY_DEPTH * 0.5 + 0.05), 0.035, 6),
			palette.get_material("silver_deep"), "SignStay%d" % side))

	var frame := Forms.mesh_node(
		Geometry.rounded_box(Vector3(board, 0.74, 0.22), 0.09, 4),
		palette.get_material("graphite"), "SignFrame")
	frame.position = Vector3(0.0, y, -0.05)
	root.add_child(frame)

	# The recess. Darker than the frame around it, so the letters have
	# somewhere to be bright against.
	var recess := Forms.mesh_node(
		Geometry.rounded_box(Vector3(board - 0.22, 0.54, 0.06), 0.04, 3),
		palette.get_material("graphite_deep"), "SignRecess")
	recess.position = Vector3(0.0, y, 0.05)
	root.add_child(recess)

	# A bar under the letters, not a lit panel behind them. A full-area
	# backlight blooms over its own legend and takes the word away, which is
	# how the sign ended up blank in the first place.
	var glow := Forms.mesh_node(
		Geometry.rounded_box(Vector3(board - 0.34, 0.045, 0.02), 0.015, 2),
		palette.get_material("lit_sign"), "SignBacklight", false)
	glow.position = Vector3(0.0, y - 0.23, 0.07)
	root.add_child(glow)

	var word := Node3D.new()
	word.name = "SignLegend"
	word.position = Vector3(0.0, y, 0.115)
	root.add_child(word)
	Forms.legend(word, palette.get_material("lit_white"), "START",
		board - 0.86, 0.40, 0.07, 0.34)

	# Top and bottom bezels rather than one: a single band on top makes the
	# board look like it is hanging, and two make it look built.
	for edge in 2:
		var lift: float = 0.42 if edge == 0 else -0.42
		var bezel := Forms.mesh_node(
			Geometry.rounded_box(Vector3(board + 0.08, 0.10, 0.26), 0.035, 3),
			palette.get_material("gold"), "SignBezel%d" % edge, false)
		bezel.position = Vector3(0.0, y + lift, -0.05)
		root.add_child(bezel)

	# End caps, and a cyan pip on each: the sign gets the same corner
	# hardware as every other assembly in the machine.
	for side in 2:
		var x: float = (board * 0.5 + 0.02) * (1.0 if side == 0 else -1.0)
		var cap := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.16, 0.80, 0.30), 0.06, 3),
			palette.get_material("graphite_soft"), "SignCap%d" % side)
		cap.position = Vector3(x, y, -0.05)
		root.add_child(cap)

		var pip := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.07, 0.07, 0.03), 0.02, 2),
			palette.get_material("neon_cyan"), "SignPip%d" % side, false)
		pip.position = Vector3(x, y + 0.30, 0.10)
		root.add_child(pip)

	# Two lamps raking the sign face, which is what a real product shot does
	# and what stops the sign reading as a flat emissive rectangle.
	for side in 2:
		var x: float = (DECK_WIDTH * 0.5 - 0.60) * (1.0 if side == 0 else -1.0)
		var lamp := Forms.mesh_node(
			Geometry.rounded_disc(0.075, 0.10, 0.03, 16, 2),
			palette.get_material("chrome"), "SignLamp%d" % side, false)
		lamp.position = Vector3(x, y + 0.50, 0.16)
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
