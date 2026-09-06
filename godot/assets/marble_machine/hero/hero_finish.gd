extends RefCounted

## STAGE 7 - THE FINISH ARENA.
##
## The bottom of the frame, the warm end of the colour story, and the second of
## the machine's two hero modules. A tower that ends in a plinth ends; a tower
## that ends in a lit gold arena with a checkered floor and a FINISH sign over
## it *concludes*, and that difference is most of why the three-stage slice read
## as an incomplete prototype.
##
##            ╭─────────  FINISH  ─────────╮     lit sign, gold frame
##       ╭────┴────────────────────────────┴────╮
##       │   ╭──── gold guard, warm band ────╮   │
##       │   │  ╭── arrival trough, warm ──╮ │   │
##       │   │  │   ▓▒▓▒ checkered pad ▒▓  │ │   │   the finish marking
##       │   │  ╰──────────────────────────╯ │   │
##       │   ╰──── eight gold bollards ──────╯   │
##       ╰──── graphite drum, six radial legs ───╯
##
## ## The floor is a real checker, not a texture
##
## Sixty-four moulded tiles on an eight-by-eight pad, alternating pearl and
## graphite, clipped to a circle. A painted checker would be one flat surface
## under a heavy warm wash and would go to mud; tiles have thickness, so each
## one keeps an edge highlight and a shadow of its own and the motif survives
## both the wash and the shrink to phone size. It is about four thousand
## triangles, which is a fair price for the single object that says "race".
##
## ## Warm, but not orange
##
## The zone is gold and warm white - `GOLD`, `GOLD_LIGHT` and `pearl_warm` -
## deliberately distinct from the split's `ORANGE`. Two warm zones that share a
## hue collapse into one; separating the finale's gold from the risk route's
## orange is what keeps the bottom third of the machine reading as two events.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Layout := preload("res://assets/marble_machine/hero/hero_layout.gd")

const RADIUS := Layout.FINISH_RADIUS
const TROUGH_OUTER := RADIUS - 0.52
const TROUGH_INNER := 1.98      # where the podium begins
const TROUGH_DROP := 0.30
const PODIUM_TOP := 0.16
const GUARD_TOP := 0.94
const PAD_TILES := 8
const PAD_RADIUS := 1.72


static func action_clearance() -> Dictionary:
	return {
		"shape": "cylinder",
		"centre": Vector3(0.0, 0.2, 0.0),
		"radius": TROUGH_OUTER,
		"height": GUARD_TOP + TROUGH_DROP + 0.4,
	}


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "FinishHero"

	_trough(root, palette)
	_podium(root, palette)
	_checker(root, palette)
	_rim(root, palette)
	_bollards(root, palette)
	_sign(root, palette)
	_understructure(root, palette)
	return root


static func _trough_y(radius: float) -> float:
	## The arrival trough: a shallow annular valley between the guard and the
	## podium, so racers that come in fast settle instead of scattering.
	var span := TROUGH_OUTER - TROUGH_INNER
	if span <= 0.001:
		return 0.0
	var t: float = clampf((radius - TROUGH_INNER) / span, 0.0, 1.0)
	return -TROUGH_DROP * sin(t * PI)


static func _trough(root: Node3D, palette) -> void:
	var profile: Array = []
	for step in 19:
		var radius: float = lerpf(TROUGH_INNER, TROUGH_OUTER,
			float(step) / 18.0)
		profile.append(Vector2(radius, _trough_y(radius)))
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile, false), 72),
		palette.get_material("running_warm"), "Trough"))

	var under: Array = []
	for point in profile:
		under.append(Vector2((point as Vector2).x, (point as Vector2).y - 0.22))
	root.add_child(Forms.mesh_node(
		Geometry.lathe(under, Geometry.profile_normals(under, true), 72),
		palette.get_material("graphite"), "TroughUnder"))

	# The warm ring under the trough's outer shoulder: the arena's own light
	# source, and the reason the whole module glows from inside itself.
	var ring := Forms.mesh_node(
		Forms.hoop(TROUGH_OUTER - 0.16, 0.075, 64, 8),
		palette.get_material("lit_gold_wash"), "TroughGlow", false)
	ring.position = Vector3(0.0, -0.10, 0.0)
	root.add_child(ring)


static func _podium(root: Node3D, palette) -> void:
	## The raised centre the checkered pad sits on: two gold-banded steps.
	var lower := Forms.mesh_node(
		Geometry.rounded_disc(TROUGH_INNER + 0.04, 0.34, 0.12, 56, 4),
		palette.get_material("pearl_warm"), "PodiumLower")
	lower.position = Vector3(0.0, -0.02, 0.0)
	root.add_child(lower)

	var upper := Forms.mesh_node(
		Geometry.rounded_disc(PAD_RADIUS + 0.22, 0.24, 0.09, 52, 4),
		palette.get_material("pearl_warm_shade"), "PodiumUpper")
	upper.position = Vector3(0.0, PODIUM_TOP - 0.10, 0.0)
	root.add_child(upper)

	var band := Forms.mesh_node(
		Forms.hoop(TROUGH_INNER + 0.02, 0.06, 56, 8),
		palette.get_material("gold"), "PodiumBand", false)
	band.position = Vector3(0.0, 0.10, 0.0)
	root.add_child(band)

	var lit := Forms.mesh_node(
		Forms.hoop(PAD_RADIUS + 0.24, 0.05, 52, 8),
		palette.get_material("neon_gold"), "PodiumLight", false)
	lit.position = Vector3(0.0, PODIUM_TOP - 0.02, 0.0)
	root.add_child(lit)

	Forms.bolt_ring(root, palette.get_material("chrome"), 22,
		TROUGH_INNER - 0.16, 0.14, 0.055, 0.05)


static func _checker(root: Node3D, palette) -> void:
	## The finish marking: an eight-by-eight tiled pad clipped to a circle.
	var pad := Node3D.new()
	pad.name = "CheckerPad"
	pad.position = Vector3(0.0, PODIUM_TOP, 0.0)
	root.add_child(pad)

	var pitch := PAD_RADIUS * 2.0 / float(PAD_TILES)
	var tile := Geometry.rounded_box(
		Vector3(pitch * 0.94, 0.09, pitch * 0.94), 0.018, 2)
	var light = palette.get_material("checker_light")
	var dark = palette.get_material("checker_dark")

	for row in PAD_TILES:
		for column in PAD_TILES:
			var x: float = (float(column) - float(PAD_TILES - 1) * 0.5) * pitch
			var z: float = (float(row) - float(PAD_TILES - 1) * 0.5) * pitch
			# Clipped to the podium's circle: a square pad on a round podium
			# is the one thing that would make the arena read as two parts.
			if Vector2(x, z).length() > PAD_RADIUS - pitch * 0.30:
				continue
			var node := Forms.mesh_node(
				tile, dark if (row + column) % 2 == 0 else light,
				"Tile%d_%d" % [row, column], false)
			node.position = Vector3(x, 0.0, z)
			pad.add_child(node)

	# A gold kerb around the pad, and a small chrome centre boss: the pad
	# needs an edge or the tiles look scattered on the podium.
	pad.add_child(Forms.mesh_node(
		Forms.hoop(PAD_RADIUS - 0.02, 0.055, 52, 8),
		palette.get_material("gold"), "Kerb", false))

	var boss := Forms.mesh_node(
		Geometry.rounded_disc(0.24, 0.13, 0.05, 20, 3),
		palette.get_material("chrome"), "CentreBoss", false)
	boss.position = Vector3(0.0, 0.07, 0.0)
	pad.add_child(boss)


static func _rim(root: Node3D, palette) -> void:
	## The outer wall: a pearl rim, a gold inlay and a low acrylic guard.
	var profile: Array = [
		Vector2(TROUGH_OUTER - 0.02, -0.06),
		Vector2(TROUGH_OUTER + 0.14, 0.04),
		Vector2(RADIUS - 0.22, 0.16),
		Vector2(RADIUS - 0.04, 0.11),
		Vector2(RADIUS, -0.06),
		Vector2(RADIUS - 0.06, -0.28),
		Vector2(RADIUS - 0.28, -0.38),
		Vector2(TROUGH_OUTER - 0.02, -0.32),
		Vector2(TROUGH_OUTER - 0.02, -0.06),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile), 72),
		palette.get_material("pearl_warm"), "Rim"))

	var inlay := Forms.mesh_node(
		Forms.hoop(RADIUS - 0.16, 0.05, 72, 8),
		palette.get_material("gold"), "RimInlay", false)
	inlay.position = Vector3(0.0, 0.17, 0.0)
	root.add_child(inlay)

	var edge := Forms.mesh_node(
		Forms.hoop(RADIUS - 0.005, 0.055, 72, 8),
		palette.get_material("neon_gold"), "RimGlow", false)
	edge.position = Vector3(0.0, -0.06, 0.0)
	root.add_child(edge)

	var outer: Array = [
		Vector2(RADIUS - 0.24, 0.14),
		Vector2(RADIUS - 0.08, 0.38),
		Vector2(RADIUS + 0.02, 0.66),
		Vector2(RADIUS + 0.08, GUARD_TOP - 0.06),
	]
	root.add_child(Forms.mesh_node(
		V2Forms.shell_lathe(outer, 0.10, 72, false),
		palette.get_material("acrylic_gold"), "Guard", false))

	var coping: Array = [
		Vector2(RADIUS + 0.00, GUARD_TOP - 0.04),
		Vector2(RADIUS - 0.02, GUARD_TOP + 0.05),
		Vector2(RADIUS + 0.08, GUARD_TOP + 0.09),
		Vector2(RADIUS + 0.17, GUARD_TOP + 0.05),
		Vector2(RADIUS + 0.15, GUARD_TOP - 0.04),
		Vector2(RADIUS + 0.00, GUARD_TOP - 0.04),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(coping, Geometry.profile_normals(coping), 72),
		palette.get_material("pearl_warm"), "Coping"))

	var mouth := Forms.mesh_node(
		Forms.hoop(RADIUS + 0.08, 0.045, 72, 8),
		palette.get_material("gold"), "MouthBead", false)
	mouth.position = Vector3(0.0, GUARD_TOP + 0.09, 0.0)
	root.add_child(mouth)


static func _bollards(root: Node3D, palette) -> void:
	## Eight gold posts around the rim, each with a warm lamp on it.
	##
	## The reference's arena is ringed with lit uprights and they do two
	## things: they break the rim's silhouette so the arena is not one smooth
	## disc, and they are the machine's lowest lights, which is what makes the
	## bottom of the frame the warmest part of it.
	var ring := Node3D.new()
	ring.name = "Bollards"
	root.add_child(ring)

	for index in 8:
		var bearing := deg_to_rad(22.5 + 45.0 * float(index))
		var direction := Vector3(cos(bearing), 0.0, sin(bearing))
		var post := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.20, 0.86, 0.20), 0.07, 3),
			palette.get_material("gold_dark"), "Post%d" % index)
		post.position = direction * (RADIUS - 0.14) + Vector3(0.0, 0.50, 0.0)
		post.rotation.y = -bearing
		ring.add_child(post)

		var lamp := Forms.mesh_node(
			Geometry.rounded_disc(0.13, 0.20, 0.06, 14, 3),
			palette.get_material("neon_gold"), "Lamp%d" % index, false)
		lamp.position = direction * (RADIUS - 0.14) + Vector3(0.0, 1.02, 0.0)
		ring.add_child(lamp)


static func _sign(root: Node3D, palette) -> void:
	## FINISH, on a gold-framed gantry standing behind the arena.
	##
	## Four placements were tried before this one and each failed the same
	## way: anywhere inside the arena's own radius puts the board in the same
	## volume as the compression channel dropping through the middle of it,
	## and the word came out as "FIN". So the sign steps *outside* and *up* -
	## radius +1.25 at bearing 244, on two tall legs, a metre and a half above
	## the guard - where nothing in the machine crosses it from any camera in
	## the sweep. It is a finish gantry rather than a plaque, which is also
	## what a race would actually build.
	##
	## Behind, because a sign across the front of the arena would be exactly
	## the "major brace across the finish" the brief forbids.
	var bearing := deg_to_rad(244.0)
	var direction := Vector3(cos(bearing), 0.0, sin(bearing))

	var pivot := Node3D.new()
	pivot.name = "FinishSign"
	pivot.position = direction * (RADIUS + 1.25) + Vector3(0.0, 2.86, 0.0)
	# Faced at the hero bearing rather than radially outward: a sign square
	# to its own radius is edge-on from every camera but one, and this is the
	# module's whole identity read.
	pivot.rotation.y = deg_to_rad(22.0)
	pivot.rotation.x = deg_to_rad(10.0)
	root.add_child(pivot)

	pivot.add_child(Forms.mesh_node(
		Geometry.rounded_box(Vector3(3.30, 0.84, 0.24), 0.11, 4),
		palette.get_material("gold_dark"), "Frame"))

	var face := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.92, 0.52, 0.10), 0.05, 3),
		palette.get_material("lit_gold_wash"), "Face", false)
	face.position = Vector3(0.0, 0.0, 0.12)
	pivot.add_child(face)

	var text := TextMesh.new()
	text.text = "FINISH"
	text.font_size = 96
	text.pixel_size = 0.0068
	text.depth = 0.05
	text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var letters := Forms.mesh_node(text, palette.get_material("checker_dark"),
		"Letters", false)
	letters.position = Vector3(0.0, 0.0, 0.20)
	pivot.add_child(letters)

	pivot.add_child(Forms.mesh_node(
		Geometry.tube([Vector3(-1.58, 0.42, 0.10), Vector3(1.58, 0.42, 0.10)],
			0.028, 8),
		palette.get_material("gold"), "Bead", false))

	# Two legs down onto the rim, and a chequered flag motif either side of
	# the board so the sign carries the race read as well as the word.
	for side in [1.0, -1.0]:
		var leg := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.24, 3.10, 0.30), 0.09, 3),
			palette.get_material("gold_dark"),
			"Leg%s" % ("R" if side > 0.0 else "L"))
		leg.position = direction * (RADIUS + 1.25) \
			+ Vector3(0.0, 1.02, 0.0) \
			+ Vector3(cos(deg_to_rad(22.0)), 0.0, -sin(deg_to_rad(22.0))) \
			* side * 1.26
		root.add_child(leg)

		var flag := Node3D.new()
		flag.name = "Flag%s" % ("R" if side > 0.0 else "L")
		flag.position = Vector3(side * 1.82, 0.0, 0.14)
		pivot.add_child(flag)
		for row in 3:
			for column in 3:
				var node := Forms.mesh_node(
					Geometry.rounded_box(Vector3(0.14, 0.14, 0.05), 0.013, 2),
					palette.get_material("checker_light"
						if (row + column) % 2 == 0 else "checker_dark"),
					"Sq%d_%d" % [row, column], false)
				node.position = Vector3((float(column) - 1.0) * 0.15,
					(float(row) - 1.0) * 0.15, 0.0)
				flag.add_child(node)


static func _understructure(root: Node3D, palette) -> void:
	## The dark drum and six radial legs the arena stands on.
	##
	## The brief asks for a dark structural underside, and it is also what
	## stops the arena reading as a coin lying on the cliff: a lit disc with
	## visible legs under it is a *building*, and this is the last object in
	## the frame before the void.
	var under := Node3D.new()
	under.name = "Understructure"
	root.add_child(under)

	var drum := Forms.mesh_node(
		Forms.hub_housing(RADIUS - 1.10, 1.34),
		palette.get_material("graphite"), "Drum")
	drum.position = Vector3(0.0, -1.10, 0.0)
	under.add_child(drum)

	var skirt := Forms.mesh_node(
		Geometry.rounded_disc(RADIUS - 0.46, 0.24, 0.09, 56, 3),
		palette.get_material("graphite_deep"), "Skirt")
	skirt.position = Vector3(0.0, -0.52, 0.0)
	under.add_child(skirt)

	var band := Forms.mesh_node(
		Forms.hoop(RADIUS - 1.04, 0.07, 40, 8),
		palette.get_material("gold"), "DrumBand", false)
	band.position = Vector3(0.0, -0.86, 0.0)
	under.add_child(band)

	var glow := Forms.mesh_node(
		Forms.hoop(RADIUS - 0.42, 0.055, 56, 8),
		palette.get_material("lit_gold_wash"), "SkirtGlow", false)
	glow.position = Vector3(0.0, -0.66, 0.0)
	under.add_child(glow)

	for index in 6:
		var bearing := deg_to_rad(30.0 + 60.0 * float(index))
		var direction := Vector3(cos(bearing), 0.0, sin(bearing))
		var leg: Array = [
			direction * (RADIUS - 0.62) + Vector3(0.0, -0.60, 0.0),
			direction * (RADIUS - 0.90) + Vector3(0.0, -1.40, 0.0),
			direction * (RADIUS - 1.86) + Vector3(0.0, -2.30, 0.0),
		]
		under.add_child(Forms.mesh_node(
			Geometry.tube(leg, 0.17, 10),
			palette.get_material("graphite"), "Leg%d" % index))

		var shoe := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.46, 0.20, 0.34), 0.08, 3),
			palette.get_material("graphite_soft"), "LegShoe%d" % index)
		shoe.position = direction * (RADIUS - 0.62) + Vector3(0.0, -0.66, 0.0)
		shoe.rotation.y = -bearing
		under.add_child(shoe)

	Forms.bolt_ring(under, palette.get_material("chrome"), 24, RADIUS - 0.56,
		-0.40, 0.06, 0.05)
