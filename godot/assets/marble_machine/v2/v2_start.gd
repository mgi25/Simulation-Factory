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


static func build_sill(palette) -> Node3D:
	## The handover at the front of the pod: a gold sill and three lane ribs.
	##
	## What used to be here was a separate funnel - a wide moulded fan that
	## narrowed to a throat. It was the right idea and the wrong part: seen
	## from any hero angle it was a large white triangle, and a shape with no
	## length reads as a skirt rather than as a chute.
	##
	## The transition is now made by the *track* instead. `FEED_CONTROLS`
	## starts at the pod's lip with a large entry flare, so the signature
	## channel itself opens to the full width of the tray and closes to single
	## file within a couple of units. One component, one material language,
	## and the same rolled lip running all the way from the start line to the
	## bowl. All that is left here is the sill it pours over.
	var root := Node3D.new()
	root.name = "Sill"

	var band := Forms.mesh_node(
		Geometry.rounded_box(Vector3(BAY_PITCH * float(BAYS) + 0.26, 0.16, 0.30),
			0.06, 3),
		palette.get_material("gold"), "Band")
	band.position = Vector3(0.0, -0.14, POD_DEPTH * 0.5 + 0.16)
	root.add_child(band)

	var apron := Forms.mesh_node(
		Geometry.rounded_box(Vector3(BAY_PITCH * float(BAYS) + 0.10, 0.20, 0.62),
			0.09, 3),
		palette.get_material("pearl_shade"), "Apron")
	apron.position = Vector3(0.0, -0.30, POD_DEPTH * 0.5 + 0.38)
	root.add_child(apron)

	for index in [2, 4, 6]:
		var x: float = (float(index) - float(BAYS) * 0.5) * BAY_PITCH
		root.add_child(Forms.mesh_node(
			Geometry.tube([
				Vector3(x, -0.16, POD_DEPTH * 0.5 + 0.10),
				Vector3(x * 0.86, -0.24, POD_DEPTH * 0.5 + 0.66)], 0.05, 8),
			palette.get_material("silver"), "LaneRib%d" % index, false))
	return root
