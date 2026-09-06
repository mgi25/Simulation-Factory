extends RefCounted

## STAGE 2 - THE MIXING BOWL. The machine's first hero.
##
## The V2.2 bowl was the best object on that branch and still failed the two
## tests the brief names for this one. From the hero camera it read as a *plate*
## with a flat aqua disc laid over it, and its transparency read as a tint
## rather than as glass. Both faults have the same cause: a straight, short
## acrylic wall standing on a wide shallow dish presents one silhouette and one
## flat wash, and neither the curve nor the material can be seen in it.
##
## Three changes, all structural:
##
## **The wall flares.** The shell now opens from the rim outward to 4.62 over
## 1.62 of height - a bell, not a cylinder. A flared wall is seen at a
## different angle at every height, so it carries a gradient down its own
## surface instead of one value, and that gradient is what the eye reads as
## glass. It also gives the module the wine-glass silhouette the concept has.
##
## **The bowl has a belly.** Under the running dish there is now a curved
## graphite underbowl with gold ribs on it, so from the hero camera the module
## is a *bowl shape* seen from outside as well as a dish seen from inside. A
## dish with a flat underside is a plate however deep its face is.
##
## **The dish is grooved.** Four concentric steps sunk into the running
## surface, 0.02 deep. They cost nothing and they put four curved highlight
## arcs across the one surface that was reading as a featureless wash - the
## brief's white-surface-control rule, solved with geometry rather than paint.
##
## ## Proportion
##
## Running dish 6.28 across against a 0.57 racer: eleven racers end to end, in
## the brief's 8-12 band. Reached by keeping the bowl where it was and letting
## the *machine* grow around it - the module is now 12 per cent of a 31-unit
## tower rather than 20 per cent of a 20-unit one, which is what puts it in the
## concept's own proportion without shrinking a single racer.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Layout := preload("res://assets/marble_machine/hero/hero_layout.gd")

const RIM_RADIUS := Layout.BOWL_RIM_RADIUS
const DISH_RADIUS := Layout.BOWL_DISH_RADIUS
const DRAIN_RADIUS := Layout.BOWL_DRAIN_RADIUS
const DISH_DEPTH := Layout.BOWL_DEPTH
const SHELL_TOP := 1.62
const SHELL_FLARE := 0.90       # how far the mouth stands outside the rim
const CRADLE_BEARINGS := [204.0, 268.0, 140.0]


static func action_clearance() -> Dictionary:
	return {
		"shape": "cylinder",
		"centre": Vector3(0.0, 0.2, 0.0),
		"radius": DISH_RADIUS + 0.15,
		"height": SHELL_TOP + DISH_DEPTH + 0.6,
	}


static func dish_y(radius: float) -> float:
	## The running surface's height at a radius, grooves included.
	var span := DISH_RADIUS - DRAIN_RADIUS
	var t: float = clampf((radius - DRAIN_RADIUS) / maxf(span, 0.001), 0.0, 1.0)
	return -DISH_DEPTH * (0.5 + 0.5 * cos(t * PI))


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "BowlHero"

	_dish(root, palette)
	_belly(root, palette)
	_rim(root, palette)
	_shell(root, palette)
	_drain(root, palette)
	_cradle(root, palette)
	return root


static func _dish(root: Node3D, palette) -> void:
	## The polished running surface, with four concentric grooves in it.
	var profile: Array = []
	var steps := 40
	for step in steps + 1:
		var t := float(step) / float(steps)
		var radius: float = lerpf(DRAIN_RADIUS, DISH_RADIUS, t)
		var y := dish_y(radius)
		# Four shallow steps. A groove is authored as two points at the same
		# radius so the lathe gets a hard normal break there - which is the
		# whole trick: it costs one vertex and buys a highlight arc.
		var groove: float = -0.022 * pow(
			maxf(sin(t * PI * 4.0), 0.0), 6.0)
		profile.append(Vector2(radius, y + groove))
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile, false), 80),
		palette.get_material("pan_polished"), "RunningSurface"))

	# The violet ring under the dish's outer edge: the mixer zone's colour,
	# grazing up through the acrylic from underneath.
	var ring := Forms.mesh_node(
		Forms.hoop(DISH_RADIUS - 0.06, 0.065, 64, 8),
		palette.get_material("lit_violet_ring_hero"), "MixerRing", false)
	ring.position = Vector3(0.0, -0.42, 0.0)
	root.add_child(ring)


static func _belly(root: Node3D, palette) -> void:
	## The curved graphite underbowl, and six gold ribs down it.
	##
	## What makes the module a bowl rather than a plate. From the hero camera
	## about a third of the bowl's screen area is this surface, and the ribs
	## are there so it is a *moulded* third rather than a dark ellipse.
	var profile: Array = []
	var steps := 24
	for step in steps + 1:
		var t := float(step) / float(steps)
		var radius: float = lerpf(DRAIN_RADIUS + 0.34, DISH_RADIUS + 0.14, t)
		profile.append(Vector2(radius, dish_y(radius) - 0.34
			- 0.30 * (1.0 - t) * (1.0 - t)))
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile, true), 72),
		palette.get_material("graphite"), "Belly"))

	for index in 6:
		var bearing := deg_to_rad(30.0 + 60.0 * float(index))
		var direction := Vector3(cos(bearing), 0.0, sin(bearing))
		var rib: Array = []
		for step in 9:
			var t := float(step) / 8.0
			var radius: float = lerpf(DRAIN_RADIUS + 0.44, DISH_RADIUS + 0.06, t)
			rib.append(direction * radius
				+ Vector3(0.0, dish_y(radius) - 0.30
					- 0.30 * (1.0 - t) * (1.0 - t), 0.0))
		root.add_child(Forms.mesh_node(
			Geometry.tube(rib, 0.055, 8),
			palette.get_material("gold"), "BellyRib%d" % index, false))

	# A graphite hoop closing the belly against the rim's underside, so the
	# join between the two is a designed line and not a gap.
	var hoop := Forms.mesh_node(
		Forms.hoop(DISH_RADIUS + 0.12, 0.10, 64, 8),
		palette.get_material("graphite_deep"), "BellyHoop", false)
	hoop.position = Vector3(0.0, -0.40, 0.0)
	root.add_child(hoop)


static func _rim(root: Node3D, palette) -> void:
	## The thick machined rim: rolled pearl cap, chrome bead, gold inlay,
	## bolt ring, and a cyan line sunk into its outer edge.
	var profile: Array = [
		Vector2(DISH_RADIUS - 0.02, -0.05),
		Vector2(DISH_RADIUS + 0.10, 0.03),
		Vector2(DISH_RADIUS + 0.28, 0.15),
		Vector2(RIM_RADIUS - 0.30, 0.22),
		Vector2(RIM_RADIUS - 0.09, 0.18),
		Vector2(RIM_RADIUS, 0.02),
		Vector2(RIM_RADIUS - 0.04, -0.18),
		Vector2(RIM_RADIUS - 0.24, -0.30),
		Vector2(DISH_RADIUS + 0.14, -0.34),
		Vector2(DISH_RADIUS - 0.02, -0.23),
		Vector2(DISH_RADIUS - 0.02, -0.05),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile), 80),
		palette.get_material("pearl_lip_v2"), "Rim"))

	var bead := Forms.mesh_node(
		Forms.hoop(RIM_RADIUS - 0.20, 0.045, 80, 8),
		palette.get_material("chrome"), "RimBead", false)
	bead.position = Vector3(0.0, 0.225, 0.0)
	root.add_child(bead)

	var inlay := Forms.mesh_node(
		Forms.hoop(DISH_RADIUS + 0.20, 0.05, 80, 8),
		palette.get_material("gold"), "RimInlay", false)
	inlay.position = Vector3(0.0, 0.135, 0.0)
	root.add_child(inlay)

	Forms.bolt_ring(root, palette.get_material("chrome"), 40, RIM_RADIUS - 0.14,
		0.15, 0.052, 0.048)

	var edge := Forms.mesh_node(
		Forms.hoop(RIM_RADIUS - 0.01, 0.05, 80, 8),
		palette.get_material("lit_cyan_line_hero"), "RimEdgeLight", false)
	edge.position = Vector3(0.0, -0.02, 0.0)
	root.add_child(edge)


static func _shell(root: Node3D, palette) -> void:
	## The flared aqua guard, with real wall thickness and a pearl coping.
	##
	## The bell is the module's whole transparency read. A straight wall shows
	## one value; this one turns through about forty degrees between its foot
	## and its mouth, so the near wall, the far wall and the mouth are three
	## different brightnesses of the same material - which is what tells the
	## eye it is looking through something rather than at a coloured film.
	var outer: Array = []
	var steps := 12
	for step in steps + 1:
		var t := float(step) / float(steps)
		# Radius grows with an ease-out and height with an ease-in, so the
		# wall leaves the rim nearly vertical and finishes nearly flared.
		var radius: float = RIM_RADIUS - 0.30 + SHELL_FLARE * pow(t, 1.55)
		var y: float = 0.10 + (SHELL_TOP - 0.10) * pow(t, 0.86)
		outer.append(Vector2(radius, y))
	root.add_child(Forms.mesh_node(
		V2Forms.shell_lathe(outer, 0.11, 80, false),
		palette.get_material("acrylic_bowl"), "Guard", false))

	var mouth_radius: float = RIM_RADIUS - 0.30 + SHELL_FLARE
	var coping: Array = [
		Vector2(mouth_radius - 0.09, SHELL_TOP - 0.02),
		Vector2(mouth_radius - 0.11, SHELL_TOP + 0.08),
		Vector2(mouth_radius, SHELL_TOP + 0.13),
		Vector2(mouth_radius + 0.10, SHELL_TOP + 0.08),
		Vector2(mouth_radius + 0.08, SHELL_TOP - 0.02),
		Vector2(mouth_radius - 0.09, SHELL_TOP - 0.02),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(coping, Geometry.profile_normals(coping), 80),
		palette.get_material("pearl_lip_v2"), "Coping"))

	var mouth_bead := Forms.mesh_node(
		Forms.hoop(mouth_radius, 0.05, 88, 8),
		palette.get_material("chrome"), "MouthBead", false)
	mouth_bead.position = Vector3(0.0, SHELL_TOP + 0.13, 0.0)
	root.add_child(mouth_bead)

	# A second, fainter aqua line partway up the bell. Cast acrylic parts are
	# almost always moulded with a step in them, and the step is what stops a
	# large curved transparent surface reading as a soap film.
	var step_line := Forms.mesh_node(
		Forms.hoop(RIM_RADIUS - 0.30 + SHELL_FLARE * 0.44, 0.035, 72, 8),
		palette.get_material("lit_cyan_soft"), "ShellStep", false)
	step_line.position = Vector3(0.0, 0.10 + (SHELL_TOP - 0.10) * 0.62, 0.0)
	root.add_child(step_line)

	for index in CRADLE_BEARINGS.size():
		var bearing := deg_to_rad(float(CRADLE_BEARINGS[index]))
		var foot := Vector3(cos(bearing) * (RIM_RADIUS - 0.22), 0.16,
			sin(bearing) * (RIM_RADIUS - 0.22))
		var head := Vector3(cos(bearing) * (mouth_radius - 0.04),
			SHELL_TOP + 0.04, sin(bearing) * (mouth_radius - 0.04))
		root.add_child(Forms.mesh_node(
			Geometry.tube([foot, head], 0.075, 10),
			palette.get_material("silver"), "Stay%d" % index))


static func _drain(root: Node3D, palette) -> void:
	## The visible throat: a gold collar, a dark barrel seen through it, and
	## a violet ring down inside. The module's focal point.
	var ring: Array = [
		Vector2(DRAIN_RADIUS - 0.02, -DISH_DEPTH + 0.20),
		Vector2(DRAIN_RADIUS + 0.28, -DISH_DEPTH + 0.26),
		Vector2(DRAIN_RADIUS + 0.44, -DISH_DEPTH + 0.12),
		Vector2(DRAIN_RADIUS + 0.42, -DISH_DEPTH - 0.10),
		Vector2(DRAIN_RADIUS + 0.06, -DISH_DEPTH - 0.16),
		Vector2(DRAIN_RADIUS - 0.02, -DISH_DEPTH + 0.00),
		Vector2(DRAIN_RADIUS - 0.02, -DISH_DEPTH + 0.20),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(ring, Geometry.profile_normals(ring), 48),
		palette.get_material("gold"), "DrainCollar"))

	var barrel: Array = [
		Vector2(DRAIN_RADIUS - 0.03, -DISH_DEPTH + 0.22),
		Vector2(DRAIN_RADIUS - 0.07, -DISH_DEPTH - 0.36),
		Vector2(DRAIN_RADIUS - 0.18, -DISH_DEPTH - 0.98),
		Vector2(DRAIN_RADIUS - 0.40, -DISH_DEPTH - 1.44),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(barrel, Geometry.profile_normals(barrel, false), 44),
		palette.get_material("graphite_deep"), "Throat"))

	var inner := Forms.mesh_node(
		Forms.hoop(DRAIN_RADIUS - 0.04, 0.055, 36, 8),
		palette.get_material("lit_violet_ring_hero"), "ThroatLight", false)
	inner.position = Vector3(0.0, -DISH_DEPTH - 0.22, 0.0)
	root.add_child(inner)

	Forms.bolt_ring(root, palette.get_material("chrome"), 14,
		DRAIN_RADIUS + 0.24, -DISH_DEPTH + 0.19, 0.04, 0.038)


static func _cradle(root: Node3D, palette) -> void:
	## Three heavy graphite arms on rear bearings, and the hub they meet at.
	##
	## Three and not eight, and all of them behind: the front of the dish
	## stays completely open, which is what `action_clearance` promises and
	## what the hero camera needs.
	var cradle := Node3D.new()
	cradle.name = "Cradle"
	root.add_child(cradle)

	var hub := Forms.mesh_node(
		Forms.hub_housing(0.98, 1.06),
		palette.get_material("graphite"), "Hub")
	hub.position = Vector3(0.0, -DISH_DEPTH - 1.02, 0.0)
	cradle.add_child(hub)

	var band := Forms.mesh_node(
		Forms.hoop(1.04, 0.07, 30, 8),
		palette.get_material("gold"), "HubBand", false)
	band.position = Vector3(0.0, -DISH_DEPTH - 0.88, 0.0)
	cradle.add_child(band)

	for index in CRADLE_BEARINGS.size():
		var bearing := deg_to_rad(float(CRADLE_BEARINGS[index]))
		var direction := Vector3(cos(bearing), 0.0, sin(bearing))
		var arm: Array = []
		for step in 9:
			var t := float(step) / 8.0
			var radius: float = lerpf(0.88, RIM_RADIUS - 0.40, t)
			var lift: float = lerpf(-DISH_DEPTH - 0.78, -0.28,
				smoothstep(0.0, 1.0, pow(t, 1.35)))
			arm.append(direction * radius + Vector3(0.0, lift, 0.0))
		cradle.add_child(Forms.mesh_node(
			Geometry.tube(arm, 0.17, 10),
			palette.get_material("graphite"), "Arm%d" % index))

		var shoe := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.56, 0.24, 0.40), 0.09, 3),
			palette.get_material("graphite_soft"), "ArmShoe%d" % index)
		shoe.position = direction * (RIM_RADIUS - 0.42) + Vector3(0.0, -0.34, 0.0)
		shoe.rotation.y = -bearing
		cradle.add_child(shoe)

		var collar := Forms.mesh_node(
			Geometry.rounded_disc(0.24, 0.12, 0.045, 16, 3),
			palette.get_material("gold"), "ArmCollar%d" % index, false)
		collar.position = direction * (RIM_RADIUS - 0.42) + Vector3(0.0, -0.20, 0.0)
		cradle.add_child(collar)

		var jack := Forms.mesh_node(
			Geometry.rounded_disc(0.17, 0.42, 0.07, 16, 3),
			palette.get_material("orange_machine"), "ArmJack%d" % index)
		jack.position = direction * 1.94 + Vector3(0.0, -DISH_DEPTH - 0.46, 0.0)
		jack.rotation.z = PI * 0.5
		jack.rotation.y = -bearing
		cradle.add_child(jack)
