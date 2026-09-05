extends RefCounted

## The mixing bowl: the machine's primary landmark.
##
## Built as one moulded shell rather than as a stack of parts. The whole body -
## running dish, rim, outer flank and underside - is a single lathe of a single
## closed profile, so the highlight that runs round the rim is continuous and
## the underside is genuinely the *same component* seen from below. The
## style-lock bowl was a dish with a separate ring balanced on it, and the seam
## between them is visible in every frame of that render.
##
## ## What "premium toy component" means here, concretely
##
## Four things, none of which the previous bowls had all of:
##
## **A thick rim with a top face.** A dish that ends in an edge is a plate. A
## dish that turns over into a flat machined band, carries a gold insert on
## that band, and returns down an outer flank is a moulded part. The band is
## about 0.4 units wide against a 2.5 unit dish - visible at hero distance,
## which is the test.
##
## **A guard that stands off the rim.** The acrylic wall does not sit on the
## rim, it sits *outboard* of it on its own shoulder, so there is a shadow gap
## between the two. That gap is what makes the acrylic read as a separate cast
## piece instead of as a coloured continuation of the shell.
##
## **A cradle, not a stalk.** The bowl is held by curved arms that visibly
## reach up and take it under the flank. Weight has to appear supported.
##
## **A drain that is a hole.** A dark aperture with a gold collar around it,
## with the underside of the shell visible through the rim gap. The concept's
## bowl has exactly this and it is the detail that says the marbles go
## somewhere.
##
## Local origin is the rim top face, centred, so a caller positions the bowl by
## the height it wants the rim at and never has to know the depth.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")

const INNER_RADIUS := 2.52
const DEPTH := 1.02
const DRAIN_RADIUS := 0.56
const SHELL := 0.19
const RIM_OUTER := 2.98


static func drain_local() -> Vector3:
	## Where the track picks up: the centre of the aperture, at its underside.
	return Vector3(0.0, -DEPTH - SHELL, 0.0)


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "HeroBowl"

	_shell(root, palette)
	_rim_hardware(root, palette)
	_guard(root, palette)
	_drain(root, palette)
	_cradle(root, palette)

	return root


# --- the body -------------------------------------------------------------

static func _shell(root: Node3D, palette) -> void:
	## Dish, rim, flank and underside as one closed lathe.
	##
	## The profile is read drain-first and anticlockwise in the (radius,
	## height) plane, which is why it asks `profile_normals` for the *inward*
	## family: traversed that way the running surface's normal comes out
	## pointing up into the bowl and the underside's comes out pointing down,
	## which is what they physically are.
	var dish: Array = Forms.bowl_profile(INNER_RADIUS, DEPTH, DRAIN_RADIUS, 16)

	var profile: Array = dish.duplicate()
	# Up and over the rim: a short inner round, a flat machined top face, and
	# a shoulder the guard will stand on.
	profile.append_array([
		Vector2(INNER_RADIUS + 0.06, 0.03),
		Vector2(INNER_RADIUS + 0.13, 0.11),
		Vector2(INNER_RADIUS + 0.22, 0.17),
		Vector2(INNER_RADIUS + 0.34, 0.19),
		Vector2(RIM_OUTER - 0.10, 0.19),
		Vector2(RIM_OUTER - 0.02, 0.14),
		Vector2(RIM_OUTER, 0.04),
		Vector2(RIM_OUTER, -0.20),
		Vector2(RIM_OUTER - 0.06, -0.33),
		Vector2(RIM_OUTER - 0.22, -0.40),
	])
	# The underside: the dish again, thinner and lower. Same curve, so the
	# component has an even wall - the thing an eye reads as moulded.
	for index in range(dish.size() - 1, -1, -1):
		var point: Vector2 = dish[index]
		profile.append(Vector2(maxf(point.x - 0.05, 0.0), point.y - SHELL))
	profile.append(dish[0])

	var body := Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile, false), 72),
		palette.get_material("pearl_shell"), "Shell")
	root.add_child(body)

	# A brighter inset ring on the running surface, where the field circulates.
	# One value step, not a stripe: it gives the dish an interior landmark so
	# the eye can read its curvature instead of a single flat gradient.
	var lane: Array = [
		Vector2(INNER_RADIUS * 0.52, -DEPTH * 0.44),
		Vector2(INNER_RADIUS * 0.60, -DEPTH * 0.36),
		Vector2(INNER_RADIUS * 0.60, -DEPTH * 0.36),
		Vector2(INNER_RADIUS * 0.86, -DEPTH * 0.13),
	]
	var lane_node := Forms.mesh_node(
		Geometry.lathe(lane, Geometry.profile_normals(lane, false), 72),
		palette.get_material("pearl_shade"), "LaneInset", false)
	lane_node.position = Vector3(0.0, 0.006, 0.0)
	root.add_child(lane_node)


# --- rim ------------------------------------------------------------------

static func _rim_hardware(root: Node3D, palette) -> void:
	## The machined band, its gold insert, and the light under the flank.
	var insert_radius := INNER_RADIUS + 0.40
	var insert := Forms.mesh_node(
		Forms.hoop(insert_radius, 0.055, 64, 10),
		palette.get_material("gold"), "RimInsert", false)
	insert.position = Vector3(0.0, 0.205, 0.0)
	root.add_child(insert)

	var cap := Forms.mesh_node(
		Forms.hoop(RIM_OUTER - 0.03, 0.05, 64, 10),
		palette.get_material("pearl_lip"), "RimCap", false)
	cap.position = Vector3(0.0, 0.16, 0.0)
	root.add_child(cap)

	# The practical. Tucked under the flank so the *bowl* is lit by it and the
	# lamp itself is a thin line - a visible bulb reads as a prop, a visible
	# wash reads as a product.
	var glow_key := "neon_cyan" if palette.variant == "spine" else "neon_violet"
	var glow := Forms.mesh_node(
		Forms.hoop(RIM_OUTER + 0.015, 0.042, 64, 8),
		palette.get_material(glow_key), "RimGlow", false)
	glow.position = Vector3(0.0, -0.12, 0.0)
	root.add_child(glow)

	var bolt_count := 24 if palette.variant == "deck" else 16
	Forms.bolt_ring(root, palette.get_material("chrome"), bolt_count,
		insert_radius + 0.16, 0.20, 0.055, 0.045)

	# Four clamps holding the guard down onto its shoulder.
	var clamp_mesh := Geometry.rounded_box(Vector3(0.22, 0.13, 0.34), 0.05, 3)
	for index in Forms.ring_positions(4, RIM_OUTER - 0.30, PI * 0.25).size():
		var at: Vector3 = Forms.ring_positions(4, RIM_OUTER - 0.30, PI * 0.25)[index]
		var clamp := Forms.mesh_node(clamp_mesh, palette.get_material("silver"),
			"GuardClamp%d" % index, false)
		clamp.position = at + Vector3(0.0, 0.22, 0.0)
		clamp.rotation.y = -atan2(at.z, at.x)
		root.add_child(clamp)


# --- guard ----------------------------------------------------------------

static func _guard(root: Node3D, palette) -> void:
	## The aqua acrylic wall, standing outboard of the rim on its shoulder.
	var height: float = 1.42
	match palette.variant:
		"deck":
			height = 1.00
		"spine":
			height = 1.24

	var base_radius := RIM_OUTER - 0.16
	var wall: Array = [
		Vector2(base_radius, 0.20),
		Vector2(base_radius + 0.04, 0.34),
		Vector2(base_radius + 0.14, height * 0.55),
		Vector2(base_radius + 0.30, height * 0.90),
		Vector2(base_radius + 0.38, height),
	]
	var key := "acrylic_aqua_deep" if palette.variant == "deck" else "acrylic_aqua"
	var glass := Forms.mesh_node(
		Geometry.lathe(wall, Geometry.profile_normals(wall, true), 72),
		palette.get_material(key), "GuardWall", false)
	root.add_child(glass)

	# The top edge, in near-clear stock. A cast panel always has a thicker,
	# lighter edge than its face, and without it the wall's silhouette
	# dissolves against a dark backdrop.
	var edge := Forms.mesh_node(
		Forms.hoop(base_radius + 0.38, 0.05, 64, 10),
		palette.get_material("acrylic_clear"), "GuardEdge", false)
	edge.position = Vector3(0.0, height, 0.0)
	root.add_child(edge)

	# Vertical mullions: six thin silver posts up the wall. They are what give
	# the transparent surface something to shade against, and they read as the
	# frame of a guard rather than as decoration.
	var mullion := Geometry.rounded_box(Vector3(0.07, height - 0.18, 0.10), 0.025, 3)
	for index in 6:
		var angle := TAU * float(index) / 6.0 + PI * 0.08
		var post := Forms.mesh_node(mullion, palette.get_material("silver"),
			"Mullion%d" % index, false)
		var radius: float = base_radius + 0.22
		post.position = Vector3(cos(angle) * radius, 0.20 + (height - 0.18) * 0.5,
			sin(angle) * radius)
		post.rotation.y = -angle
		root.add_child(post)


# --- drain ----------------------------------------------------------------

static func _drain(root: Node3D, palette) -> void:
	## A real aperture: a dark throat, a gold collar, a lit inner edge.
	var throat: Array = [
		Vector2(DRAIN_RADIUS + 0.09, -DEPTH + 0.10),
		Vector2(DRAIN_RADIUS, -DEPTH - 0.02),
		Vector2(DRAIN_RADIUS - 0.04, -DEPTH - 0.34),
		Vector2(DRAIN_RADIUS - 0.04, -DEPTH - 0.78),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(throat, Geometry.profile_normals(throat, true), 40),
		palette.get_material("graphite_deep"), "DrainThroat"))

	var collar := Forms.mesh_node(
		Forms.hoop(DRAIN_RADIUS + 0.10, 0.062, 44, 10),
		palette.get_material("gold"), "DrainCollar", false)
	collar.position = Vector3(0.0, -DEPTH + 0.10, 0.0)
	root.add_child(collar)

	var lit := Forms.mesh_node(
		Forms.hoop(DRAIN_RADIUS + 0.20, 0.032, 44, 6),
		palette.get_material("neon_cyan"), "DrainLight", false)
	lit.position = Vector3(0.0, -DEPTH + 0.145, 0.0)
	root.add_child(lit)


# --- cradle ---------------------------------------------------------------

static func _cradle(root: Node3D, palette) -> void:
	## What holds the bowl up, and it must look like it could.
	var arm_count := 4
	var reach := RIM_OUTER - 0.26
	var phase := PI * 0.25
	match palette.variant:
		"deck":
			arm_count = 8
			phase = 0.0
		"spine":
			arm_count = 3
			phase = PI * 0.5

	var hoop_radius := reach * 0.72
	var hub := Forms.mesh_node(
		Forms.hoop(hoop_radius, 0.10, 48, 8),
		palette.get_material("graphite"), "CradleHoop")
	hub.position = Vector3(0.0, -DEPTH - 0.36, 0.0)
	root.add_child(hub)

	var boss := Forms.mesh_node(
		Geometry.rounded_disc(DRAIN_RADIUS + 0.42, 0.26, 0.09, 32, 3),
		palette.get_material("graphite_soft"), "CradleBoss")
	boss.position = Vector3(0.0, -DEPTH - 0.30, 0.0)
	root.add_child(boss)

	for index in arm_count:
		var angle := phase + TAU * float(index) / float(arm_count)
		var outer := Vector3(cos(angle) * reach, -0.34, sin(angle) * reach)
		var mid := Vector3(cos(angle) * reach * 0.92, -DEPTH * 0.62 - 0.30,
			sin(angle) * reach * 0.92)
		var inner := Vector3(cos(angle) * hoop_radius, -DEPTH - 0.36,
			sin(angle) * hoop_radius)
		var arm_path := Forms.smooth_path([outer, mid, inner], 8)
		root.add_child(Forms.mesh_node(
			Geometry.tube(arm_path, 0.085, 8),
			palette.get_material("graphite"), "CradleArm%d" % index))

		var pad := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.34, 0.13, 0.26), 0.05, 3),
			palette.get_material("gold"), "CradlePad%d" % index, false)
		pad.position = outer + Vector3(0.0, 0.02, 0.0)
		pad.rotation.y = -angle
		root.add_child(pad)
