extends RefCounted

## START V2 - a moulded launch pod.
##
## The marble-v1 start was a narrow technical chute: racers in single file, no
## launch moment, no identity. The prior lab's was a rectangular deck with rails
## and a sign floating over it on posts. Both are the same mistake - a *stage*
## with things standing on it, rather than a product with a silhouette.
##
## This one is a pod. One moulded pearl body with a big fillet on every edge,
## chunky end blocks holding the gate mechanism, a recessed silver tray cut into
## its top, and the sign carried in a frame that grows out of the body's own
## back wall instead of perching above it on stilts. From any angle the outline
## is a single continuous shape, which is the thing that makes a toy photograph
## as a toy.
##
##          ╭──────────  START  ──────────╮      lit sign in a graphite frame
##      ╭───┴────────────────────────────┴───╮
##      │  ▏●▕▏●▕▏●▕▏●▕▏●▕▏●▕▏●▕▏●▕  │      eight bays, all visible
##      ╰──┬──────── gate ──────────┬───╯
##         ╰────── dark chassis ─────╯
##
## ## Eight abreast, and what that costs
##
## The brief requires all eight racers visible side by side, and a bay wide
## enough for a marble is the hard floor on the pod's width. That makes the
## start wider relative to the bowl than the reference concept's is - the
## concept cheats by drawing its marbles small. The trade is taken deliberately:
## "all eight racers readable at the line" is a named requirement and "matches
## the reference's width ratio" is not.
##
## ## Zone colour
##
## Cyan and white, per the brief's zone identity. The only warm things on it are
## the gate hardware and the machinery under the deck - which is the rule the
## whole palette runs on: warmth marks the parts that move.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")

const BAYS := 8
const BAY_PITCH := 0.63
const FIN_THICK := 0.065
const TRAY_TOP := -0.02        # local y of the surface a racer rests on
const POD_WIDTH := 5.45
const POD_DEPTH := 2.44
const POD_HEIGHT := 1.05
const GATE_Z := 1.16

# --- V2.2 mixer -----------------------------------------------------------
#
# The V2.1 answer to start-lane advantage was a full-width open deflector deck.
# It worked as a mechanism and failed as composition: six units of exposed
# Plinko board directly under the pod became the largest, busiest object in the
# upper half of the machine and stole the hierarchy from the bowl.
#
# The mechanism is kept and put back inside the machine. A compact housing
# tucked under the gate, the width of the pod's own chassis and about a third
# of the deck's footprint, with the deflector rows *behind an acrylic window*
# rather than standing in the open. You can see it working; it no longer
# competes to be looked at. Two rows instead of four, because the housing is
# followed by a converging throat and then a bowl, and because the object's job
# in the frame is now to read as machinery rather than to be a diagram.
#
# Whether the mixing is sufficient is a question for PyBullet, not for a
# render. Nothing here claims it - the geometry is arranged so the question can
# be asked later, and `PIN_PITCH - 2 * PIN_RADIUS` is still the number a
# Monte-Carlo pass would want to vary.
const MIX_HALF := 2.30
const MIX_FRONT_Z := 2.32
const MIX_BACK_Z := 1.30
const MIX_TOP_Y := -0.44
const MIX_BOTTOM_Y := -1.36
const THROAT_Y := -1.86
const THROAT_Z := 2.52
const PIN_PITCH := 0.86
const PIN_RADIUS := 0.115
const PIN_HEIGHT := 0.34
const PIN_ROWS := 2


static func bay_x(index: int) -> float:
	## The centreline of one bay, in pod-local X.
	return (float(index) - float(BAYS - 1) * 0.5) * BAY_PITCH


static func bay_positions(marble_radius: float) -> Array:
	## Where each racer sits on the line, in pod-local space.
	var out: Array = []
	for index in BAYS:
		out.append(Vector3(bay_x(index), TRAY_TOP + marble_radius, 0.10))
	return out


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "StartV2"

	_body(root, palette)
	_bays(root, palette)
	_gate(root, palette)
	_sign(root, palette)
	_chassis(root, palette)
	return root


static func _body(root: Node3D, palette) -> void:
	## The moulded shell: one big filleted volume plus two heavier end blocks.
	##
	## The end blocks are the medium-scale move that stops the pod reading as
	## a loaf. They are slightly taller and slightly deeper than the body, in
	## a brighter pearl, so the silhouette steps twice across its width and
	## the eye gets a proportion to read rather than one long edge.
	var shell = palette.get_material("pearl_shell")
	var lip = palette.get_material("pearl_lip_v2")

	var body := Forms.mesh_node(
		Geometry.rounded_box(Vector3(POD_WIDTH, POD_HEIGHT, POD_DEPTH), 0.30, 4),
		shell, "Body")
	body.position = Vector3(0.0, -POD_HEIGHT * 0.5 - 0.02, 0.0)
	root.add_child(body)

	for side in [1.0, -1.0]:
		var suffix := "R" if side > 0.0 else "L"
		var block := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.62, 1.20, 2.68), 0.28, 4),
			lip, "EndBlock%s" % suffix)
		block.position = Vector3(side * (POD_WIDTH * 0.5 - 0.10), -0.42, 0.0)
		root.add_child(block)

		# A gold cap on each block: the hardware read, and the only metal up
		# here besides the gate.
		var cap := Forms.mesh_node(
			Geometry.rounded_disc(0.30, 0.12, 0.05, 20, 3),
			palette.get_material("gold"), "BlockCap%s" % suffix, false)
		cap.position = Vector3(side * (POD_WIDTH * 0.5 - 0.10), 0.26, 0.0)
		root.add_child(cap)

	# A graphite belt round the pod's waist, and a shaded skirt under it.
	#
	# Without them the pod is one continuous bright pearl volume a metre and a
	# half deep, and a single value across that much area reads as a blank
	# rather than as a moulding. The belt gives the silhouette a horizontal
	# division at the height where a real product would have its parting line,
	# and the skirt puts the bottom third into shade so the body has a top and
	# a bottom instead of a middle.
	var belt := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(POD_WIDTH + 0.10, 0.22, POD_DEPTH + 0.08), 0.09, 3),
		palette.get_material("graphite_soft"), "Belt")
	belt.position = Vector3(0.0, -0.72, 0.0)
	root.add_child(belt)

	var skirt := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(POD_WIDTH - 0.24, 0.42, POD_DEPTH - 0.20), 0.16, 4),
		palette.get_material("pearl_shade"), "Skirt")
	skirt.position = Vector3(0.0, -1.02, 0.0)
	root.add_child(skirt)

	var beltTrim := Forms.mesh_node(
		Geometry.tube([
			Vector3(-(POD_WIDTH * 0.5 - 0.30), -0.60, POD_DEPTH * 0.5 + 0.02),
			Vector3(POD_WIDTH * 0.5 - 0.30, -0.60, POD_DEPTH * 0.5 + 0.02)],
			0.03, 8),
		palette.get_material("gold"), "BeltTrim", false)
	root.add_child(beltTrim)

	# Back wall: the sign frame grows out of this rather than off stilts.
	var back := Forms.mesh_node(
		Geometry.rounded_box(Vector3(POD_WIDTH - 0.60, 0.74, 0.40), 0.16, 4),
		lip, "BackWall")
	back.position = Vector3(0.0, 0.24, -POD_DEPTH * 0.5 + 0.10)
	root.add_child(back)

	# Front lip, with the zone's cyan line sunk into its top edge.
	var front := Forms.mesh_node(
		Geometry.rounded_box(Vector3(POD_WIDTH - 0.50, 0.34, 0.34), 0.14, 4),
		shell, "FrontLip")
	front.position = Vector3(0.0, -0.02, POD_DEPTH * 0.5 - 0.03)
	root.add_child(front)

	var strip := Forms.mesh_node(
		Geometry.tube([
			Vector3(-(POD_WIDTH * 0.5 - 0.42), 0.10, POD_DEPTH * 0.5 + 0.10),
			Vector3(POD_WIDTH * 0.5 - 0.42, 0.10, POD_DEPTH * 0.5 + 0.10)],
			0.045, 8),
		palette.get_material("lit_cyan_line"), "FrontLight", false)
	root.add_child(strip)


static func _bays(root: Node3D, palette) -> void:
	## The recessed silver tray and the nine fins that divide it.
	var tray := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(BAY_PITCH * float(BAYS) + 0.10, 0.16, 1.94), 0.05, 3),
		palette.get_material("track_floor_v2"), "Tray", false)
	tray.position = Vector3(0.0, TRAY_TOP - 0.08, 0.05)
	root.add_child(tray)

	var fin := Geometry.rounded_box(Vector3(FIN_THICK, 0.30, 1.86), 0.028, 3)
	for index in BAYS + 1:
		var x: float = (float(index) - float(BAYS) * 0.5) * BAY_PITCH
		var node := Forms.mesh_node(fin, palette.get_material("silver"),
			"Fin%d" % index)
		node.position = Vector3(x, TRAY_TOP + 0.10, 0.05)
		root.add_child(node)

	# A lit bead in the floor of each bay: the lane read, and where the cyan
	# actually comes from. Small emitters in recesses, never painted faces.
	var bead := Geometry.rounded_disc(0.055, 0.03, 0.012, 10, 2)
	for index in BAYS:
		var node := Forms.mesh_node(bead,
			palette.get_material("lit_cyan_line"), "LaneBead%d" % index, false)
		node.position = Vector3(bay_x(index), TRAY_TOP + 0.005, -0.78)
		root.add_child(node)


static func _gate(root: Node3D, palette) -> void:
	## The synchronised release: one acrylic bar on gold pivots, with an
	## orange paddle standing in front of every bay.
	##
	## Attractive because it is *one* mechanism rather than eight - a single
	## bar spanning the pod says the release is synchronised far more clearly
	## than eight independent doors would, and it keeps the front of the pod
	## legible instead of turning it into a row of small parts.
	var gold = palette.get_material("gold")
	var gate := Node3D.new()
	gate.name = "Gate"
	root.add_child(gate)

	for side in [1.0, -1.0]:
		var x: float = side * (POD_WIDTH * 0.5 - 0.26)
		gate.add_child(Forms.mesh_node(
			Geometry.tube([Vector3(x, -0.06, GATE_Z), Vector3(x, 0.74, GATE_Z)],
				0.075, 10),
			gold, "Post%s" % ("R" if side > 0.0 else "L")))
		var boss := Forms.mesh_node(
			Geometry.rounded_disc(0.20, 0.16, 0.06, 18, 3),
			palette.get_material("orange_machine"),
			"Actuator%s" % ("R" if side > 0.0 else "L"))
		boss.position = Vector3(x, 0.60, GATE_Z)
		boss.rotation.z = PI * 0.5
		gate.add_child(boss)

	var bar := Forms.mesh_node(
		Geometry.rounded_box(Vector3(POD_WIDTH - 0.34, 0.20, 0.13), 0.055, 3),
		palette.get_material("acrylic_aqua_deep"), "Bar", false)
	bar.position = Vector3(0.0, 0.60, GATE_Z)
	gate.add_child(bar)

	var rail := Forms.mesh_node(
		Geometry.tube([
			Vector3(-(POD_WIDTH * 0.5 - 0.30), 0.74, GATE_Z),
			Vector3(POD_WIDTH * 0.5 - 0.30, 0.74, GATE_Z)], 0.038, 8),
		palette.get_material("chrome"), "BarTrim", false)
	gate.add_child(rail)

	var paddle := Geometry.rounded_box(Vector3(0.54, 0.34, 0.07), 0.026, 3)
	for index in BAYS:
		var node := Forms.mesh_node(paddle,
			palette.get_material("orange_machine"), "Paddle%d" % index)
		node.position = Vector3(bay_x(index), TRAY_TOP + 0.13, GATE_Z - 0.06)
		gate.add_child(node)


static func _sign(root: Node3D, palette) -> void:
	## A large readable START, in a frame carried by the pod's own back wall.
	##
	## Real 3D text rather than a bright rectangle. A blank lit panel is what
	## the previous two attempts shipped, and a blank panel is a lamp - it
	## reads as a light source, not as signage, and the module loses the
	## landmark identity the brief asks for. The letters are emissive and the
	## frame around them is dark, so the sign is the brightest small thing in
	## the upper third of the machine and the eye starts there.
	var frame_y := 1.62
	var frame_z := -1.02
	var tilt := deg_to_rad(9.0)

	var pivot := Node3D.new()
	pivot.name = "Sign"
	pivot.position = Vector3(0.0, frame_y, frame_z)
	pivot.rotation.x = tilt
	root.add_child(pivot)

	pivot.add_child(Forms.mesh_node(
		Geometry.rounded_box(Vector3(4.36, 1.00, 0.28), 0.13, 4),
		palette.get_material("graphite_soft"), "Frame"))

	var face := Forms.mesh_node(
		Geometry.rounded_box(Vector3(3.90, 0.60, 0.10), 0.055, 3),
		palette.get_material("sign_face"), "Face", false)
	face.position = Vector3(0.0, 0.0, 0.13)
	pivot.add_child(face)

	var text := TextMesh.new()
	text.text = "START"
	text.font_size = 96
	text.pixel_size = 0.0082
	text.depth = 0.05
	text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var letters := Forms.mesh_node(text, palette.get_material("lit_white"),
		"Letters", false)
	letters.position = Vector3(0.0, 0.0, 0.21)
	pivot.add_child(letters)

	# Corner hardware, and a chrome bead along the top of the frame.
	for side in [1.0, -1.0]:
		var boss := Forms.mesh_node(
			Geometry.rounded_disc(0.16, 0.13, 0.05, 16, 3),
			palette.get_material("gold"),
			"SignBoss%s" % ("R" if side > 0.0 else "L"), false)
		boss.position = Vector3(side * 2.04, 0.0, 0.10)
		boss.rotation.x = PI * 0.5
		pivot.add_child(boss)
	pivot.add_child(Forms.mesh_node(
		Geometry.tube([Vector3(-2.08, 0.50, 0.10), Vector3(2.08, 0.50, 0.10)],
			0.035, 8),
		palette.get_material("chrome"), "SignBead", false))

	# The two shoulders that carry the frame off the back wall. Short, thick
	# and part of the body's outline - not stilts.
	for side in [1.0, -1.0]:
		var arm := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.34, 1.10, 0.44), 0.14, 3),
			palette.get_material("graphite"),
			"SignArm%s" % ("R" if side > 0.0 else "L"))
		arm.position = Vector3(side * 1.72, 0.96, frame_z - 0.02)
		root.add_child(arm)


static func _chassis(root: Node3D, palette) -> void:
	## The dark mechanical underside: chassis, drums, collars, a warm line.
	##
	## Every module in the reference has a dark bottom, and it is doing two
	## jobs: it separates a bright module from whatever is beneath it, and it
	## is where all the machinery lives so the top can stay clean.
	var chassis := Node3D.new()
	chassis.name = "Chassis"
	root.add_child(chassis)

	var main := Forms.mesh_node(
		Geometry.rounded_box(Vector3(4.55, 0.72, 1.98), 0.22, 4),
		palette.get_material("graphite_deep"), "Deck")
	main.position = Vector3(0.0, -1.42, -0.06)
	chassis.add_child(main)

	var keel := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.05, 0.56, 1.36), 0.20, 4),
		palette.get_material("graphite"), "Keel")
	keel.position = Vector3(0.0, -1.96, -0.06)
	chassis.add_child(keel)

	for side in [1.0, -1.0]:
		var suffix := "R" if side > 0.0 else "L"
		var drum := Forms.mesh_node(
			Geometry.rounded_disc(0.34, 0.52, 0.11, 22, 3),
			palette.get_material("orange_machine"), "Drum%s" % suffix)
		drum.position = Vector3(side * 1.44, -1.46, 0.64)
		drum.rotation.z = PI * 0.5
		chassis.add_child(drum)

		var collar := Forms.mesh_node(
			Geometry.rounded_disc(0.20, 0.18, 0.06, 18, 3),
			palette.get_material("gold"), "DrumCollar%s" % suffix, false)
		collar.position = Vector3(side * 1.70, -1.46, 0.64)
		collar.rotation.z = PI * 0.5
		chassis.add_child(collar)

	var rack := Node3D.new()
	rack.name = "Rack"
	rack.position = Vector3(0.0, -1.86, 1.06)
	chassis.add_child(rack)
	Forms.equipment_rack(rack,
		palette.get_material("graphite_soft"),
		palette.get_material("gold"),
		palette.get_material("lit_cyan_line"), 3, 3.0)

	chassis.add_child(Forms.mesh_node(
		Geometry.tube([Vector3(-2.05, -1.08, 0.96), Vector3(2.05, -1.08, 0.96)],
			0.04, 8),
		palette.get_material("lit_cyan_line"), "SeamLight", false))


static func mixer_exit_local() -> Vector3:
	## Where the mixer hands over to the feed chute, in pod-local space.
	return Vector3(0.0, THROAT_Y, THROAT_Z)


static func pin_positions() -> Array:
	## The deflectors inside the housing, in pod-local space.
	##
	## Two staggered rows, five and six, at half a pitch of offset so a gap in
	## one sits behind a pin in the next. Generated rather than listed: a
	## physics pass rebuilds the field from the four constants above instead
	## of transcribing coordinates that would then have two sources of truth.
	var out: Array = []
	for row in PIN_ROWS:
		var z: float = lerpf(MIX_BACK_Z + 0.24, MIX_FRONT_Z - 0.26,
			float(row) / float(maxi(PIN_ROWS - 1, 1)))
		var offset := row % 2 == 1
		var count := 6 if offset else 5
		for index in count:
			var centre: float = (float(index) - float(count - 1) * 0.5) * PIN_PITCH
			out.append(Vector3(centre, MIX_BOTTOM_Y + 0.36, z))
	return out


static func build_mixer(palette) -> Node3D:
	## The release mechanism: a compact housing under the gate, then a throat.
	var root := Node3D.new()
	root.name = "Mixer"

	var mid_z := (MIX_BACK_Z + MIX_FRONT_Z) * 0.5
	var mid_y := (MIX_TOP_Y + MIX_BOTTOM_Y) * 0.5
	var depth := MIX_FRONT_Z - MIX_BACK_Z
	var height := MIX_TOP_Y - MIX_BOTTOM_Y

	# The housing. Graphite, so it reads as part of the pod's dark underside
	# rather than as a second white object hung off it.
	var housing := Forms.mesh_node(
		Geometry.rounded_box(Vector3(MIX_HALF * 2.0, height, depth), 0.16, 4),
		palette.get_material("graphite"), "Housing")
	housing.position = Vector3(0.0, mid_y, mid_z)
	root.add_child(housing)

	# No pearl shroud over it. One was tried and became a blank white box hung
	# under a white pod - the mechanism disappeared into the module it was
	# meant to sit under. The housing is dark all the way, so the pod's bright
	# body ends in a shadow and the machinery reads as machinery.
	for edge in [-1.0, 1.0]:
		var rail := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(MIX_HALF * 2.10, 0.15, 0.20), 0.06, 3),
			palette.get_material("graphite_soft"),
			"Rail%s" % ("F" if edge > 0.0 else "B"))
		rail.position = Vector3(0.0, MIX_TOP_Y, mid_z + edge * (depth * 0.5))
		root.add_child(rail)
	for side in [-1.0, 1.0]:
		var end_cap := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(0.22, 0.15, depth + 0.14), 0.06, 3),
			palette.get_material("graphite_soft"),
			"End%s" % ("R" if side > 0.0 else "L"))
		end_cap.position = Vector3(side * MIX_HALF, MIX_TOP_Y, mid_z)
		root.add_child(end_cap)

	# The window is in the *top* face, not the front. A camera twenty degrees
	# above the horizon sees a horizontal panel and only grazes a vertical
	# one, and the whole point of a window is that what is behind it can be
	# seen working.
	var window := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(MIX_HALF * 1.86, 0.07, depth * 0.74), 0.05, 3),
		palette.get_material("acrylic_guard"), "Window", false)
	window.position = Vector3(0.0, MIX_TOP_Y - 0.03, mid_z)
	root.add_child(window)

	# A lit floor under the deflectors, so the field is read against light
	# rather than against the inside of an unlit box.
	var glow := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(MIX_HALF * 1.50, 0.05, depth * 0.58), 0.02, 2),
		palette.get_material("lit_cyan_line"), "InteriorLight", false)
	glow.position = Vector3(0.0, MIX_BOTTOM_Y + 0.12, mid_z)
	root.add_child(glow)


	var post := Geometry.rounded_disc(PIN_RADIUS, PIN_HEIGHT,
		PIN_RADIUS * 0.99, 14, 4)
	var pins := Node3D.new()
	pins.name = "Pins"
	root.add_child(pins)
	var index := 0
	for at in pin_positions():
		var pin := Forms.mesh_node(post, palette.get_material("chrome"),
			"Pin%d" % index)
		pin.position = at
		pins.add_child(pin)
		index += 1

	# A gold band round the housing's top edge, and a cyan line
	# in the seam under it. The two details that say "fitting" at this size.
	var band := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(MIX_HALF * 2.06, 0.075, depth + 0.06), 0.03, 2),
		palette.get_material("gold"), "Band", false)
	band.position = Vector3(0.0, MIX_TOP_Y - height * 0.34, mid_z)
	root.add_child(band)

	root.add_child(Forms.mesh_node(
		Geometry.tube([
			Vector3(-MIX_HALF * 0.86, MIX_BOTTOM_Y + 0.10, MIX_FRONT_Z + 0.03),
			Vector3(MIX_HALF * 0.86, MIX_BOTTOM_Y + 0.10, MIX_FRONT_Z + 0.03)],
			0.035, 8),
		palette.get_material("lit_cyan_line"), "SeamLight", false))

	# The rotor drums at each end: the moving-parts read, in the zone's orange.
	for side in [1.0, -1.0]:
		var suffix := "R" if side > 0.0 else "L"
		var drum := Forms.mesh_node(
			Geometry.rounded_disc(0.26, 0.40, 0.09, 20, 3),
			palette.get_material("orange_machine"), "Drum%s" % suffix)
		drum.position = Vector3(side * (MIX_HALF + 0.06), mid_y - 0.06, mid_z)
		drum.rotation.z = PI * 0.5
		root.add_child(drum)

		var collar := Forms.mesh_node(
			Geometry.rounded_disc(0.15, 0.16, 0.05, 16, 3),
			palette.get_material("gold"), "DrumCollar%s" % suffix, false)
		collar.position = Vector3(side * (MIX_HALF + 0.28), mid_y - 0.06, mid_z)
		collar.rotation.z = PI * 0.5
		root.add_child(collar)

	# The throat: a short converging spout, gold-collared, pointing at the
	# chute's mouth. Compact on purpose - the transition is the bowl's
	# approach, not an object in its own right.
	var spout: Array = []
	var spout_normals: Array = []
	var mouth := 1.05
	var steps := 10
	for step in steps + 1:
		var t := float(step) / float(steps)
		var half: float = lerpf(MIX_HALF * 0.78, mouth, smoothstep(0.0, 1.0, t))
		var section: Array = V2Forms.ensure_ccw([
			Vector2(half, 0.30),
			Vector2(half * 0.94, -0.02),
			Vector2(0.0, -0.16),
			Vector2(-half * 0.94, -0.02),
			Vector2(-half, 0.30),
			Vector2(-half * 1.09, 0.30),
			Vector2(-half * 1.02, -0.24),
			Vector2(0.0, -0.30),
			Vector2(half * 1.02, -0.24),
			Vector2(half * 1.09, 0.30),
			Vector2(half, 0.30),
		])
		spout.append(section)
		spout_normals.append(V2Forms.section_normals(section))

	var path: Array = []
	var banks: Array = []
	for step in steps + 1:
		var t := float(step) / float(steps)
		path.append(Vector3(0.0,
			lerpf(MIX_BOTTOM_Y - 0.02, THROAT_Y, t),
			lerpf(MIX_BACK_Z + 0.34, THROAT_Z, t)))
		banks.append(0.0)
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, spout, spout_normals, banks),
		palette.get_material("pearl_shell"), "Throat"))

	var collar := Forms.mesh_node(
		Geometry.rounded_disc(mouth * 1.12, 0.16, 0.06, 24, 3),
		palette.get_material("gold"), "ThroatCollar")
	collar.position = Vector3(0.0, THROAT_Y + 0.06, THROAT_Z)
	collar.rotation.x = deg_to_rad(-34.0)
	root.add_child(collar)
	return root
