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

# --- V2.1 shuffle deck ----------------------------------------------------
#
# The fairness fix. Eight bays on a straight line feeding one chute means the
# bay a racer starts in decides where it sits in the stream, and on a chute
# that curves, the inside lane is simply shorter. That is a positional
# advantage that survives the whole first transition, which the course rules
# forbid.
#
# A deflector field destroys lane identity outright. Four staggered rows of
# pins, each gap wider than a marble and each pin narrower than the gap it
# splits, so a racer arriving in any bay leaves the deck at a lateral position
# uncorrelated with the one it started at. It is the classic answer because it
# is the *provable* one - no path through the field is shorter than another by
# construction, and the outcome does not depend on tuning a curve.
#
# It is also the right answer visually. The brief wants the start advantage
# broken by the first obstacle, and an obstacle you can see is worth more than
# a geometric trick you cannot: a wide chrome-pinned apron under the pod reads
# instantly as "the order gets scrambled here".
#
# The deck is wider than the pod on purpose. Pin pitch has to clear a marble
# in every gap including the two against the walls, and the arithmetic - six
# pins at 0.90 pitch, outermost at 2.25, plus a 0.10 pin radius - puts the
# wall at 2.95 if the edge gap is to stay above the 0.57 marble diameter. The
# step it puts in the silhouette under the pod is a bonus.
const DECK_HALF := 2.95
const DECK_ENTRY_Z := 1.40
const DECK_EXIT_Z := 3.45
const DECK_ENTRY_Y := -0.34
const DECK_EXIT_Y := -1.22
const PIN_PITCH := 0.90
const PIN_RADIUS := 0.115
const PIN_HEIGHT := 0.30
const PIN_ROWS := 4
# The mouth the deck actually hands over to. The pin field has to be full
# width for its gaps to clear a marble, but the chute below it is the hero
# section plus its entry flare - about 3.6 across - so the last stretch of the
# deck converges. The taper sits *after* every pin row, so it costs nothing in
# fairness: by the time a racer reaches it, its lateral position no longer has
# anything to do with the bay it left.
const DECK_MOUTH_HALF := 1.72
const DECK_TAPER := 0.92


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


static func deck_floor_y(z: float) -> float:
	## The deck's sloping floor at a given pod-local z.
	var t: float = clampf((z - DECK_ENTRY_Z) / (DECK_EXIT_Z - DECK_ENTRY_Z),
		0.0, 1.0)
	return lerpf(DECK_ENTRY_Y, DECK_EXIT_Y, t)


static func deck_exit_local() -> Vector3:
	## Where the deck hands over to the feed chute, in pod-local space.
	return Vector3(0.0, DECK_EXIT_Y + 0.02, DECK_EXIT_Z)


static func pin_positions() -> Array:
	## Every deflector, in pod-local space.
	##
	## Rows alternate five and six pins at half a pitch of offset, which is
	## what makes a gap in one row sit behind a pin in the next - the whole
	## mechanism. Placement is arithmetic on the row index, so two renders of
	## this deck are identical and a physics pass can rebuild the field from
	## the same four numbers rather than from a list.
	var out: Array = []
	for row in PIN_ROWS:
		var z: float = lerpf(DECK_ENTRY_Z + 0.52, DECK_EXIT_Z - 0.42,
			float(row) / float(PIN_ROWS - 1))
		var offset := row % 2 == 1
		var count := 6 if offset else 5
		for index in count:
			var centre: float = (float(index) - float(count - 1) * 0.5) * PIN_PITCH
			out.append(Vector3(centre, deck_floor_y(z), z))
	return out


static func build_shuffle(palette) -> Node3D:
	## The deflector deck: the first obstacle, and the one that makes the
	## start fair.
	var root := Node3D.new()
	root.name = "ShuffleDeck"

	var mid_z := (DECK_ENTRY_Z + DECK_EXIT_Z) * 0.5
	var mid_y := (DECK_ENTRY_Y + DECK_EXIT_Y) * 0.5
	var length := DECK_EXIT_Z - DECK_ENTRY_Z
	var drop := DECK_ENTRY_Y - DECK_EXIT_Y
	var tilt := atan2(drop, length)
	var run := sqrt(length * length + drop * drop)

	# The tray: one moulded pearl pan, tilted, with a shaded underside.
	var pan := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_HALF * 2.0, 0.24, run + 0.30),
			0.11, 4),
		palette.get_material("pearl_shell"), "Pan")
	pan.position = Vector3(0.0, mid_y - 0.13, mid_z)
	pan.rotation.x = tilt
	root.add_child(pan)

	# A recessed floor inset into the pan, several stops under the pearl.
	#
	# Without it the deck is six units of unbroken top-value white right under
	# a pod made of the same thing, and forty chrome pins standing on white
	# have nothing to be read against. The bay tray gets away with a light
	# silver because it is small; a surface this size needs the darker one.
	# Offset along the pan's own normal, not straight up: the pan is tilted
	# twenty-six degrees, so a vertical offset puts the inset barely proud at
	# the middle and inside the pan at the ends.
	var deck_up := Vector3(0.0, cos(tilt), sin(tilt))
	var floor_inset := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_HALF * 1.92, 0.14, run - 0.06),
			0.05, 3),
		palette.get_material("graphite_soft"), "Deck", false)
	floor_inset.position = pan.position + deck_up * 0.15
	floor_inset.rotation.x = tilt
	root.add_child(floor_inset)

	var under = Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_HALF * 1.72, 0.30, run - 0.20),
			0.13, 4),
		palette.get_material("graphite"), "PanUnder")
	under.position = Vector3(0.0, mid_y - 0.40, mid_z - 0.04)
	under.rotation.x = tilt
	root.add_child(under)

	# Side walls, and a lit line sunk along the inside of each.
	for side in [1.0, -1.0]:
		var suffix := "R" if side > 0.0 else "L"
		var wall := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.20, 0.46, run + 0.28), 0.08, 3),
			palette.get_material("silver"), "Wall%s" % suffix)
		wall.position = Vector3(side * DECK_HALF, mid_y + 0.12, mid_z)
		wall.rotation.x = tilt
		root.add_child(wall)

		root.add_child(Forms.mesh_node(
			Geometry.tube([
				Vector3(side * (DECK_HALF - 0.13), DECK_ENTRY_Y + 0.20,
					DECK_ENTRY_Z),
				Vector3(side * (DECK_HALF - 0.13), DECK_EXIT_Y + 0.20,
					DECK_EXIT_Z)], 0.045, 8),
			palette.get_material("lit_cyan_line"), "DeckLight%s" % suffix,
			false))

	# The pins: chrome capsules, fully rounded top and bottom.
	#
	# The fillet is the pin's whole radius, so there is no cylindrical waist
	# and no flat top. Anything less rounded reads as a canister rather than
	# as a deflector, and a separate cap on top - tried at two sizes - reads
	# as the rim of one. A marble has to glance off these, and a shape that
	# looks like it would glance is worth more than a shape with hardware on
	# it. The gold in this module lives on the sill and the exit lip instead.
	var post := Geometry.rounded_disc(PIN_RADIUS, PIN_HEIGHT,
		PIN_RADIUS * 0.99, 16, 5)
	var pins := Node3D.new()
	pins.name = "Pins"
	root.add_child(pins)
	var index := 0
	for at in pin_positions():
		var place: Vector3 = at
		var pin := Forms.mesh_node(post, palette.get_material("chrome"),
			"Pin%d" % index)
		pin.position = place + Vector3(0.0, PIN_HEIGHT * 0.5 - 0.02, 0.0)
		pins.add_child(pin)
		index += 1

	# The entry sill the tray pours over, and the exit lip it pours off.
	var sill := Forms.mesh_node(
		Geometry.rounded_box(Vector3(BAY_PITCH * float(BAYS) + 0.26, 0.16, 0.30),
			0.06, 3),
		palette.get_material("gold"), "Sill")
	sill.position = Vector3(0.0, DECK_ENTRY_Y + 0.04, DECK_ENTRY_Z - 0.10)
	root.add_child(sill)

	# The converging vanes, and a lip sized to the mouth they make.
	for side in [1.0, -1.0]:
		var suffix := "R" if side > 0.0 else "L"
		var from := Vector3(side * (DECK_HALF - 0.10), 0.0,
			DECK_EXIT_Z - DECK_TAPER)
		var to := Vector3(side * DECK_MOUTH_HALF, 0.0, DECK_EXIT_Z)
		var span := to - from
		var vane := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.18, 0.52, span.length() + 0.10),
				0.07, 3),
			palette.get_material("pearl_lip_v2"), "Vane%s" % suffix)
		vane.position = Vector3((from.x + to.x) * 0.5,
			deck_floor_y((from.z + to.z) * 0.5) + 0.16, (from.z + to.z) * 0.5)
		vane.rotation.y = atan2(span.x, span.z)
		root.add_child(vane)

		root.add_child(Forms.mesh_node(
			Geometry.tube([
				from + Vector3(0.0, deck_floor_y(from.z) + 0.40, 0.0),
				to + Vector3(0.0, deck_floor_y(to.z) + 0.40, 0.0)], 0.04, 8),
			palette.get_material("lit_cyan_line"), "VaneLight%s" % suffix,
			false))

	var lip := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_MOUTH_HALF * 2.16, 0.18, 0.34),
			0.07, 3),
		palette.get_material("gold"), "ExitLip")
	lip.position = Vector3(0.0, DECK_EXIT_Y + 0.06, DECK_EXIT_Z + 0.02)
	root.add_child(lip)

	# Two brackets carrying the deck off the pod's chassis.
	for side in [1.0, -1.0]:
		var stay := Forms.mesh_node(
			Geometry.tube([
				Vector3(side * (DECK_HALF - 0.60), -1.55, DECK_ENTRY_Z + 0.30),
				Vector3(side * (DECK_HALF - 0.30), DECK_EXIT_Y - 0.26,
					DECK_EXIT_Z - 0.20)], 0.075, 8),
			palette.get_material("graphite"),
			"DeckStay%s" % ("R" if side > 0.0 else "L"))
		root.add_child(stay)
	return root
