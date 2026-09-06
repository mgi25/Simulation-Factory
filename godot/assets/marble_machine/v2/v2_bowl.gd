extends RefCounted

## BOWL V2 - a premium transparent toy component.
##
## The marble-v1 bowl was an enormous plain cream dish: too much empty area, a
## weak housing, racers the size of pinheads, and nothing about it transparent.
## The prior lab's was better but still a cream plate with a wall on it.
##
## The fix is layering. A single lathed dish is one surface and one highlight,
## and no amount of paint makes one surface look like cast plastic. This bowl is
## seven concentric parts:
##
##      ╭───────────  aqua acrylic shell, real wall thickness  ──────────╮
##      │  ╭──────────  machined rim: pearl cap + chrome bead  ───────╮  │
##      │  │  ╭─── silver running dish, marbles circulating ───╮      │  │
##      │  │  │                  ╭─ drain throat ─╮            │      │  │
##      │  │  ╰──────────────────┴────────────────┴────────────╯      │  │
##      │  ╰────── violet ring light, under the dish's own edge ──────╯  │
##      ╰──────────── graphite cradle, three arms, behind ───────────────╯
##
## ## The transparent read
##
## The shell is a *shell*: `shell_lathe` walks the profile out and back so the
## rim has a visible wall thickness. A single-sided lathe has no edge - it ends
## in a zero-width line and the eye reads it as film. Thickness plus a backlight
## term is the whole difference between cast acrylic and a soap bubble, and it
## is why this reads as the reference's glass mixing bowl instead of as a
## coloured wash over a plate.
##
## ## Racer scale
##
## The running dish is 6.96 units across and a racer is 0.57, so about twelve fit
## end to end. That is the proportion the brief asks for: large enough that a
## collision is followable, small enough that a dozen racers still read as a
## field rather than as a crowd. It was reached by shrinking the *bowl* rather
## than by inflating the marbles.
##
## ## Action clearance
##
## `ACTION_CLEARANCE` is the volume that must stay empty from the preferred
## cameras: a cylinder over the whole running surface, from the dish up past the
## rim. The cradle arms are therefore placed on rear bearings only, and the
## shell - the one thing that does cross the sightline - is transparent. Nothing
## opaque is permitted between a front camera and the field.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")

# Local origin: the centre of the rim plane. The dish hangs below it.
const RIM_RADIUS := 4.15       # outer edge of the machined rim
const DISH_RADIUS := 3.48      # where the running surface meets the rim
const DRAIN_RADIUS := 0.70
const DISH_DEPTH := 1.16
const SHELL_TOP := 1.22        # how far the acrylic guard stands above the rim
const CRADLE_BEARINGS := [200.0, 262.0, 138.0]


static func action_clearance() -> Dictionary:
	## The volume that must stay clear of structure, in bowl-local space.
	return {
		"shape": "cylinder",
		"centre": Vector3(0.0, 0.2, 0.0),
		"radius": DISH_RADIUS + 0.15,
		"height": SHELL_TOP + DISH_DEPTH + 0.6,
	}


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "BowlV2"

	_dish(root, palette)
	_rim(root, palette)
	_shell(root, palette)
	_drain(root, palette)
	_cradle(root, palette)
	return root


static func _dish(root: Node3D, palette) -> void:
	## The silver running surface, and the violet light under its edge.
	var profile: Array = V2Forms.dish_profile(
		DISH_RADIUS, DRAIN_RADIUS, DISH_DEPTH, 18)
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile, false), 72),
		palette.get_material("dish_floor"), "RunningSurface"))

	# Underside: the same profile dropped and thickened, in pearl. Without it
	# the dish is a one-sided surface and from below the bowl has no bottom.
	var under: Array = []
	for point in profile:
		under.append(Vector2((point as Vector2).x, (point as Vector2).y - 0.16))
	root.add_child(Forms.mesh_node(
		Geometry.lathe(under, Geometry.profile_normals(under, true), 72),
		palette.get_material("pearl_shade"), "DishUnder"))

	# The mixer zone's violet, as a ring sunk under the dish's outer edge. It
	# lights the pearl underside and grazes up through the acrylic, which is
	# how a practical belongs to a module instead of sitting on it.
	var ring := Forms.mesh_node(
		Forms.hoop(DISH_RADIUS - 0.04, 0.07, 64, 8),
		palette.get_material("lit_violet_ring"), "MixerRing", false)
	ring.position = Vector3(0.0, -0.46, 0.0)
	root.add_child(ring)


static func _rim(root: Node3D, palette) -> void:
	## The thick machined rim: a rolled pearl cap, a chrome bead, a bolt ring.
	##
	## The single most important part of the module. A bowl whose wall simply
	## stops at the top reads as sheet; a bowl with a heavy rolled rim reads as
	## a moulded component that was designed to be picked up. It is also the
	## brightest band in the module and therefore what draws the eye to the
	## field inside it.
	var profile: Array = [
		Vector2(DISH_RADIUS - 0.02, -0.06),
		Vector2(DISH_RADIUS + 0.10, 0.02),
		Vector2(DISH_RADIUS + 0.30, 0.14),
		Vector2(RIM_RADIUS - 0.34, 0.21),
		Vector2(RIM_RADIUS - 0.10, 0.17),
		Vector2(RIM_RADIUS, 0.02),
		Vector2(RIM_RADIUS - 0.04, -0.18),
		Vector2(RIM_RADIUS - 0.26, -0.30),
		Vector2(DISH_RADIUS + 0.16, -0.34),
		Vector2(DISH_RADIUS - 0.02, -0.24),
		Vector2(DISH_RADIUS - 0.02, -0.06),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile), 72),
		palette.get_material("pearl_lip_v2"), "Rim"))

	var bead := Forms.mesh_node(
		Forms.hoop(RIM_RADIUS - 0.22, 0.045, 72, 8),
		palette.get_material("chrome"), "RimBead", false)
	bead.position = Vector3(0.0, 0.215, 0.0)
	root.add_child(bead)

	var inlay := Forms.mesh_node(
		Forms.hoop(DISH_RADIUS + 0.22, 0.05, 72, 8),
		palette.get_material("gold"), "RimInlay", false)
	inlay.position = Vector3(0.0, 0.125, 0.0)
	root.add_child(inlay)

	var bolts := Node3D.new()
	bolts.name = "RimBolts"
	root.add_child(bolts)
	Forms.bolt_ring(bolts, palette.get_material("chrome"), 36,
		RIM_RADIUS - 0.16, 0.14, 0.055, 0.05)

	# A cyan line sunk into the rim's outer edge: the module's own horizon,
	# and the thing that gives the bowl a readable outline against the gorge.
	var edge := Forms.mesh_node(
		Forms.hoop(RIM_RADIUS - 0.015, 0.05, 72, 8),
		palette.get_material("lit_cyan_line"), "RimEdgeLight", false)
	edge.position = Vector3(0.0, -0.02, 0.0)
	root.add_child(edge)


static func _shell(root: Node3D, palette) -> void:
	## The aqua guard: a flared acrylic wall with a real edge on it.
	var outer: Array = [
		Vector2(RIM_RADIUS - 0.30, 0.12),
		Vector2(RIM_RADIUS - 0.14, 0.34),
		Vector2(RIM_RADIUS - 0.02, 0.66),
		Vector2(RIM_RADIUS + 0.10, 1.02),
		Vector2(RIM_RADIUS + 0.30, SHELL_TOP - 0.20),
		Vector2(RIM_RADIUS + 0.44, SHELL_TOP),
	]
	root.add_child(Forms.mesh_node(
		V2Forms.shell_lathe(outer, 0.10, 72, false),
		palette.get_material("acrylic_bowl"), "Guard", false))

	# A pearl coping capping the guard's top edge. Cast acrylic in a premium
	# toy is always trimmed at its rim - an untrimmed edge is what a cheap
	# vacuum-formed part looks like.
	var coping: Array = [
		Vector2(RIM_RADIUS + 0.36, SHELL_TOP - 0.02),
		Vector2(RIM_RADIUS + 0.34, SHELL_TOP + 0.09),
		Vector2(RIM_RADIUS + 0.44, SHELL_TOP + 0.14),
		Vector2(RIM_RADIUS + 0.54, SHELL_TOP + 0.09),
		Vector2(RIM_RADIUS + 0.52, SHELL_TOP - 0.02),
		Vector2(RIM_RADIUS + 0.36, SHELL_TOP - 0.02),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(coping, Geometry.profile_normals(coping), 72),
		palette.get_material("pearl_lip_v2"), "Coping"))

	# Three stays, on the cradle's own bearings so structure lines up with
	# structure, and heavy enough to read as fittings rather than as wire.
	for index in CRADLE_BEARINGS.size():
		var bearing := deg_to_rad(float(CRADLE_BEARINGS[index]))
		var foot := Vector3(cos(bearing) * (RIM_RADIUS - 0.24), 0.16,
			sin(bearing) * (RIM_RADIUS - 0.24))
		var head := Vector3(cos(bearing) * (RIM_RADIUS + 0.36), SHELL_TOP + 0.04,
			sin(bearing) * (RIM_RADIUS + 0.36))
		root.add_child(Forms.mesh_node(
			Geometry.tube([foot, head], 0.085, 10),
			palette.get_material("silver"), "Stay%d" % index))


static func _drain(root: Node3D, palette) -> void:
	## The visible throat: a gold collar, a dark barrel, a lit inner ring.
	##
	## The reference's bowl has a real hole in it and you can see down into
	## it. That hole is the module's focal point - everything on the dish is
	## heading for it - so it gets the most hardware per square unit of
	## anything in the machine.
	# A ring, not a disc. A capped drain is a plate with a gold edge and the
	# module loses its focal point entirely - the hole has to be a hole.
	var ring: Array = [
		Vector2(DRAIN_RADIUS - 0.02, -DISH_DEPTH + 0.22),
		Vector2(DRAIN_RADIUS + 0.30, -DISH_DEPTH + 0.28),
		Vector2(DRAIN_RADIUS + 0.46, -DISH_DEPTH + 0.14),
		Vector2(DRAIN_RADIUS + 0.44, -DISH_DEPTH - 0.08),
		Vector2(DRAIN_RADIUS + 0.08, -DISH_DEPTH - 0.14),
		Vector2(DRAIN_RADIUS - 0.02, -DISH_DEPTH + 0.02),
		Vector2(DRAIN_RADIUS - 0.02, -DISH_DEPTH + 0.22),
	]
	var collar := Forms.mesh_node(
		Geometry.lathe(ring, Geometry.profile_normals(ring), 44),
		palette.get_material("gold"), "DrainCollar")
	root.add_child(collar)

	# The barrel is narrower than the hole so it is seen *through* it, and it
	# runs a full unit down so the throat has depth rather than a floor.
	var barrel: Array = [
		Vector2(DRAIN_RADIUS - 0.03, -DISH_DEPTH + 0.24),
		Vector2(DRAIN_RADIUS - 0.07, -DISH_DEPTH - 0.34),
		Vector2(DRAIN_RADIUS - 0.18, -DISH_DEPTH - 0.94),
		Vector2(DRAIN_RADIUS - 0.42, -DISH_DEPTH - 1.36),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(barrel, Geometry.profile_normals(barrel, false), 40),
		palette.get_material("graphite_deep"), "Throat"))

	var inner := Forms.mesh_node(
		Forms.hoop(DRAIN_RADIUS - 0.04, 0.055, 32, 8),
		palette.get_material("lit_violet_ring"), "ThroatLight", false)
	inner.position = Vector3(0.0, -DISH_DEPTH - 0.20, 0.0)
	root.add_child(inner)

	Forms.bolt_ring(root, palette.get_material("chrome"), 14,
		DRAIN_RADIUS + 0.26, -DISH_DEPTH + 0.21, 0.042, 0.04)


static func _cradle(root: Node3D, palette) -> void:
	## The graphite housing under the bowl: a hub, three curved arms, collars.
	##
	## Three arms and not eight. The brief's warning about a forest of rods is
	## the prior lab's actual failure - its supports were legible as noise from
	## every angle. Three heavy arms on rear bearings read as a designed
	## cradle, leave the front of the dish completely open, and cast three
	## clean shadows instead of a hatch pattern.
	var cradle := Node3D.new()
	cradle.name = "Cradle"
	root.add_child(cradle)

	var hub := Forms.mesh_node(
		Forms.hub_housing(1.05, 1.10),
		palette.get_material("graphite"), "Hub")
	hub.position = Vector3(0.0, -DISH_DEPTH - 0.86, 0.0)
	cradle.add_child(hub)

	var band := Forms.mesh_node(
		Forms.hoop(1.12, 0.075, 32, 8),
		palette.get_material("gold"), "HubBand", false)
	band.position = Vector3(0.0, -DISH_DEPTH - 0.72, 0.0)
	cradle.add_child(band)

	for index in CRADLE_BEARINGS.size():
		var bearing := deg_to_rad(float(CRADLE_BEARINGS[index]))
		var direction := Vector3(cos(bearing), 0.0, sin(bearing))
		var arm: Array = []
		for step in 9:
			var t := float(step) / 8.0
			var radius: float = lerpf(0.95, RIM_RADIUS - 0.42, t)
			var lift: float = lerpf(-DISH_DEPTH - 0.62, -0.30,
				smoothstep(0.0, 1.0, pow(t, 1.35)))
			arm.append(direction * radius + Vector3(0.0, lift, 0.0))
		cradle.add_child(Forms.mesh_node(
			Geometry.tube(arm, 0.19, 10),
			palette.get_material("graphite"), "Arm%d" % index))

		var shoe := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.62, 0.26, 0.44), 0.10, 3),
			palette.get_material("graphite_soft"), "ArmShoe%d" % index)
		shoe.position = direction * (RIM_RADIUS - 0.44) + Vector3(0.0, -0.36, 0.0)
		shoe.rotation.y = -bearing
		cradle.add_child(shoe)

		var collar := Forms.mesh_node(
			Geometry.rounded_disc(0.27, 0.13, 0.05, 18, 3),
			palette.get_material("gold"), "ArmCollar%d" % index, false)
		collar.position = direction * (RIM_RADIUS - 0.44) + Vector3(0.0, -0.22, 0.0)
		cradle.add_child(collar)

		# One orange actuator per arm: the machinery accent, placed where a
		# real cradle would take its load.
		var jack := Forms.mesh_node(
			Geometry.rounded_disc(0.20, 0.46, 0.08, 18, 3),
			palette.get_material("orange_machine"), "ArmJack%d" % index)
		jack.position = direction * 2.10 + Vector3(0.0, -DISH_DEPTH - 0.34, 0.0)
		jack.rotation.z = PI * 0.5
		jack.rotation.y = -bearing
		cradle.add_child(jack)
