extends RefCounted

## THE FINISH: a warm arena on a promontory at the end of the course.
##
## Its own file because it is the one module that has to hold the bottom of the
## frame on its own. Everything above it in the composition is a slender white
## channel on a dark mountain; if the finish is another length of channel with a
## sign over it, the course simply stops. So it is the only place where the
## course becomes *wide* - a fourteen-unit deck against a two-unit track - and
## the only place where the palette turns fully warm.
##
## Local frame: +Z is the direction of travel, the origin is the deck's centre
## at floor level, and the channel arrives at -Z.
##
##            ╭──────── FINISH ────────╮      lit gantry over the mouth
##      ─────╢  fan                    ║
##           ║   ▓░▓░▓░▓ checker       ║      the landing
##           ║   ┃┃┃┃┃┃┃┃ catch lanes  ║
##           ╰────── gold rim ─────────╯
##                 dark plinth

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const Track := preload("res://assets/marble_machine/v2/v2_track.gd")
const Modules := preload("res://assets/marble_machine/course/course_modules.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")

const DECK_WIDTH := 12.60
const DECK_DEPTH := 9.80
const DECK_THICK := 0.90
const RIM_HEIGHT := 0.86
const LANES := 8


static func build(palette, entry_local: Vector3) -> Node3D:
	## `entry_local` is where the final run ends, in this module's frame.
	var root := Node3D.new()
	root.name = "Finish"

	_deck(root, palette)
	_checker(root, palette)
	_catch(root, palette)
	_rim(root, palette)
	_mouth(root, palette, entry_local)
	_gantry(root, palette)
	_plinth(root, palette)
	return root


static func _deck(root: Node3D, palette) -> void:
	var deck := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH, DECK_THICK, DECK_DEPTH),
			0.42, 4),
		palette.get_material("pearl_warm"), "Deck")
	deck.position = Vector3(0.0, -DECK_THICK * 0.5, 0.0)
	root.add_child(deck)

	var floor_plate := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH - 1.10, 0.26,
			DECK_DEPTH - 1.10), 0.22, 3),
		palette.get_material("running_warm"), "Floor", false)
	floor_plate.position = Vector3(0.0, -0.10, 0.0)
	root.add_child(floor_plate)


static func _checker(root: Node3D, palette) -> void:
	## The race-completion cue, as geometry rather than as a texture.
	##
	## At this scale a checker *is* geometry: eight by four tiles standing a
	## couple of centimetres proud, which keeps its contrast when the whole
	## arena is under a gold wash and a flat painted pattern would grey out.
	var light = palette.get_material("checker_light")
	var dark = palette.get_material("checker_dark")
	var tile := Geometry.rounded_box(Vector3(1.28, 0.09, 1.02), 0.03, 2)
	var band := Node3D.new()
	band.name = "Checker"
	root.add_child(band)
	for row in 3:
		for column in 8:
			var node := Forms.mesh_node(tile,
				light if (row + column) % 2 == 0 else dark,
				"Tile%d_%d" % [row, column], false)
			node.position = Vector3((float(column) - 3.5) * 1.32, 0.02,
				-1.90 + float(row) * 1.06)
			band.add_child(node)


static func _catch(root: Node3D, palette) -> void:
	## Eight lanes and a backboard: where the order is finally read off.
	var group := Node3D.new()
	group.name = "Catch"
	group.position = Vector3(0.0, 0.0, 2.60)
	root.add_child(group)

	for index in LANES + 1:
		var x := (float(index) - float(LANES) * 0.5) * 1.32
		var fin := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.10, 0.62, 3.00), 0.04, 2),
			palette.get_material("pearl_lip_v2"), "Fin%d" % index, false)
		fin.position = Vector3(x, 0.22, 0.0)
		group.add_child(fin)

	for index in LANES:
		var x := (float(index) - float(LANES - 1) * 0.5) * 1.32
		var trough := Forms.mesh_node(
			Geometry.tube([Vector3(x, -0.10, -1.40), Vector3(x, -0.22, 1.34)],
				0.44, 12),
			palette.get_material("dish_polished"), "Lane%d" % index, false)
		group.add_child(trough)
		var lamp := Forms.mesh_node(
			Geometry.rounded_box(Vector3(1.02, 0.09, 0.16), 0.04, 2),
			palette.get_material("lit_gold_line"), "Lamp%d" % index, false)
		lamp.position = Vector3(x, 0.50, 1.46)
		group.add_child(lamp)

	var backboard := Forms.mesh_node(
		Geometry.rounded_box(Vector3(LANES * 1.32 + 0.40, 1.30, 0.34),
			0.14, 3),
		palette.get_material("graphite"), "Backboard")
	backboard.position = Vector3(0.0, 0.44, 1.72)
	group.add_child(backboard)
	var face := Forms.mesh_node(
		Geometry.rounded_box(Vector3(LANES * 1.32 - 0.10, 0.72, 0.12),
			0.06, 3),
		palette.get_material("lit_gold_wash"), "Face", false)
	face.position = Vector3(0.0, 0.48, 1.54)
	group.add_child(face)


static func _rim(root: Node3D, palette) -> void:
	## A gold wall round three sides, open where the channel comes in.
	var gold = palette.get_material("gold")
	var shade = palette.get_material("pearl_warm_shade")
	var lit = palette.get_material("lit_gold_wash")
	for entry in [
			[Vector3(0.0, 0.0, DECK_DEPTH * 0.5 - 0.24),
				Vector3(DECK_WIDTH - 0.5, RIM_HEIGHT, 0.42), "Front"],
			[Vector3(-DECK_WIDTH * 0.5 + 0.24, 0.0, 0.0),
				Vector3(0.42, RIM_HEIGHT, DECK_DEPTH - 0.5), "Left"],
			[Vector3(DECK_WIDTH * 0.5 - 0.24, 0.0, 0.0),
				Vector3(0.42, RIM_HEIGHT, DECK_DEPTH - 0.5), "Right"]]:
		var at: Vector3 = entry[0]
		var size: Vector3 = entry[1]
		var wall := Forms.mesh_node(Geometry.rounded_box(size, 0.16, 3),
			shade, "Rim%s" % str(entry[2]))
		wall.position = at + Vector3(0.0, size.y * 0.5 - 0.10, 0.0)
		root.add_child(wall)
		var cap := Forms.mesh_node(
			Geometry.rounded_box(Vector3(size.x + 0.14, 0.16, size.z + 0.14),
				0.07, 3), gold, "Cap%s" % str(entry[2]), false)
		cap.position = at + Vector3(0.0, size.y - 0.06, 0.0)
		root.add_child(cap)
		var line := Forms.mesh_node(
			Geometry.rounded_box(Vector3(size.x * 0.94, 0.10,
				size.z * 0.94), 0.04, 2), lit, "Line%s" % str(entry[2]), false)
		line.position = at + Vector3(0.0, size.y * 0.42, 0.0)
		root.add_child(line)


static func _mouth(root: Node3D, palette, entry_local: Vector3) -> void:
	## The channel opening onto the deck: the start's grid trough, reversed.
	##
	## Built from `course_modules.trough_section` rather than from the running
	## channel, for the same reason the start is: an apron has no keel to hang
	## under it, and a channel widened to two and a half times its section
	## drags a metre-deep white belly across the arena floor with it.
	var samples := 40
	var exit_at := Vector3(0.0, 0.30, -DECK_DEPTH * 0.5 + 4.40)
	var path: Array = []
	var sections: Array = []
	var normals: Array = []
	var banks: Array = []
	for index in samples:
		var t := float(index) / float(samples - 1)
		path.append(entry_local.lerp(exit_at, t))
		var built := Modules.trough_section(
			lerpf(1.02, 2.90, smoothstep(0.16, 1.0, t)))
		sections.append(built[0])
		normals.append(built[1])
		banks.append(0.0)
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, sections, normals, banks),
		palette.get_material("pearl_warm"), "Mouth"))

	var inner: Array = []
	var inner_normals: Array = []
	for index in samples:
		var t := float(index) / float(samples - 1)
		var built := Modules.floor_section(
			lerpf(0.97, 2.85, smoothstep(0.16, 1.0, t)))
		inner.append(built[0])
		inner_normals.append(built[1])
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, inner, inner_normals, banks),
		palette.get_material("running_warm"), "MouthFloor", false))

	for side in [1.0, -1.0]:
		var line: Array = []
		for index in samples:
			var t := float(index) / float(samples - 1)
			var half := lerpf(1.02, 2.90, smoothstep(0.16, 1.0, t)) + 0.20
			var centre: Vector3 = path[index]
			line.append(Vector3(side * half, centre.y + 0.04, centre.z))
		root.add_child(Forms.mesh_node(Geometry.tube(line, 0.055, 8),
			palette.get_material("lit_gold_line"),
			"MouthLine%s" % ("R" if side > 0.0 else "L"), false))


static func _gantry(root: Node3D, palette) -> void:
	## FINISH, over the mouth, carried on two posts on the deck's back corners.
	var span := 7.60
	for side in [1.0, -1.0]:
		var post := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.44, 3.30, 0.52), 0.16, 3),
			palette.get_material("graphite"),
			"Post%s" % ("R" if side > 0.0 else "L"))
		post.position = Vector3(side * span * 0.5, 1.55,
			-DECK_DEPTH * 0.5 + 0.90)
		root.add_child(post)
	var beam := Forms.mesh_node(
		Geometry.rounded_box(Vector3(span + 0.9, 0.42, 0.60), 0.16, 3),
		palette.get_material("graphite_soft"), "Beam")
	beam.position = Vector3(0.0, 3.10, -DECK_DEPTH * 0.5 + 0.90)
	root.add_child(beam)

	Modules.sign_panel(root, palette, "FINISH", 5.40,
		Vector3(0.0, 3.90, -DECK_DEPTH * 0.5 + 0.86),
		"lit_gold_wash", "checker_dark", false)

	for index in 7:
		var lamp := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.52, 0.14, 0.22), 0.06, 2),
			palette.get_material("lit_gold_line"), "Lamp%d" % index, false)
		lamp.position = Vector3((float(index) - 3.0) * 1.10, 2.86,
			-DECK_DEPTH * 0.5 + 0.60)
		root.add_child(lamp)


static func _plinth(root: Node3D, palette) -> void:
	## The dark base the arena stands on, and the hardware round its edge.
	# Two courses rather than one block, the lower one inset. A single slab
	# under a deck reads as a table; a stepped base reads as something built
	# on the ground it stands on, which is what a mesa arena has to do.
	var plinth := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH - 1.30, 1.50,
			DECK_DEPTH - 1.30), 0.34, 3),
		palette.get_material("graphite_deep"), "Plinth")
	plinth.position = Vector3(0.0, -1.62, 0.0)
	root.add_child(plinth)
	var footing := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH - 3.10, 2.40,
			DECK_DEPTH - 3.10), 0.30, 3),
		palette.get_material("graphite"), "Footing")
	footing.position = Vector3(0.0, -3.30, 0.0)
	root.add_child(footing)

	# Four gold pylons on the deck corners: the finale's own landmark, and
	# the thing that stops the arena reading as a flat rectangle in a wide
	# shot where none of its floor detail survives.
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			var pylon := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.46, 1.90, 0.46), 0.16, 3),
				palette.get_material("graphite"),
				"Pylon%d%d" % [int(float(sx)), int(float(sz))])
			pylon.position = Vector3(float(sx) * (DECK_WIDTH * 0.5 - 0.30),
				0.70, float(sz) * (DECK_DEPTH * 0.5 - 0.30))
			root.add_child(pylon)
			var lamp := Forms.mesh_node(
				Geometry.rounded_disc(0.26, 0.22, 0.07, 18, 3),
				palette.get_material("lit_gold_wash"),
				"PylonLamp%d%d" % [int(float(sx)), int(float(sz))], false)
			lamp.position = pylon.position + Vector3(0.0, 1.02, 0.0)
			root.add_child(lamp)
	var band := Forms.mesh_node(
		Geometry.rounded_box(Vector3(DECK_WIDTH - 1.20, 0.14,
			DECK_DEPTH - 1.20), 0.06, 3),
		palette.get_material("lit_gold_wash"), "Band", false)
	band.position = Vector3(0.0, -1.10, 0.0)
	root.add_child(band)
	Forms.bolt_ring(root, palette.get_material("gold"), 16, 4.9, -1.30,
		0.10, 0.09)
