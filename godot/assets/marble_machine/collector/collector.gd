extends RefCounted

## The collector: the machine's mechanical landmark and its warm zone.
##
## The brief asks for a silhouette that is memorable when paused, which rules
## out the obvious answer. A turntable with paddles is legible only from
## overhead; from a three-quarter hero angle it flattens into a disc with some
## lines on it. So the paddles here are *tall* - deep rounded blades standing
## well above the tray with an orange leading face - and they sit inside a
## stepped drum that gives the module a vertical profile of its own. Paused,
## the silhouette is a ring, a drum and five blades, which is readable at any
## angle.
##
## ## This module carries the frame's warmth
##
## The concept's colour plan runs cool at the top and gold at the bottom, and
## the finish arena is where the warm coverage that separates it from a Tron
## frame actually comes from. This module is the lab's equivalent: gold rim,
## orange mechanism, warm underglow, and a lit tray that throws warm bounce up
## into the underside of everything above it. It is placed lowest on purpose,
## because a warm base and a cool top is a lighting plan and a warm middle is
## a stain.
##
## `rotor` is a named child so a motion proof can spin it without any part of
## the still knowing that motion exists.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")

const RADIUS := 2.95
const TRAY_RADIUS := 2.42
const HUB_RADIUS := 0.92
const TRAY_DROP := 0.30


static func rim_local(angle: float) -> Vector3:
	## A point on the tray where a track can deliver, at the given bearing.
	return Vector3(cos(angle) * (TRAY_RADIUS - 0.30), 0.02,
		sin(angle) * (TRAY_RADIUS - 0.30))


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "Collector"

	_tray(root, palette)
	_rim(root, palette)
	_guard(root, palette)
	_mechanism(root, palette)
	_understructure(root, palette)

	return root


# --- the running surface --------------------------------------------------

static func _tray(root: Node3D, palette) -> void:
	## A shallow pearl dish between the hub and the rim, dished so a marble
	## visibly settles rather than sitting on a flat plate.
	var profile: Array = [
		Vector2(HUB_RADIUS, -TRAY_DROP),
		Vector2(HUB_RADIUS + 0.30, -TRAY_DROP - 0.04),
		Vector2(TRAY_RADIUS * 0.72, -TRAY_DROP * 0.72),
		Vector2(TRAY_RADIUS, 0.0),
		Vector2(TRAY_RADIUS + 0.10, 0.05),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile, false), 64),
		palette.get_material("track_silver"), "Tray"))

	# The floor under the dish, so the module is solid when seen from below.
	var floor_profile: Array = [
		Vector2(0.0, -TRAY_DROP - 0.22),
		Vector2(TRAY_RADIUS + 0.10, -TRAY_DROP - 0.22),
		Vector2(TRAY_RADIUS + 0.10, -TRAY_DROP - 0.10),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(floor_profile,
			Geometry.profile_normals(floor_profile, true), 64),
		palette.get_material("pearl_shade"), "TrayFloor"))

	# The warm inlay. A ring of gold set into the tray at the radius the field
	# circulates on, which is where the module's warmth reads from above.
	var inlay := Forms.mesh_node(
		Forms.hoop(TRAY_RADIUS * 0.80, 0.075, 56, 10),
		palette.get_material("gold"), "TrayInlay", false)
	inlay.position = Vector3(0.0, -TRAY_DROP * 0.55, 0.0)
	root.add_child(inlay)

	var inlay_glow := Forms.mesh_node(
		Forms.hoop(TRAY_RADIUS * 0.62, 0.038, 56, 8),
		palette.get_material("lit_gold"), "TrayGlow", false)
	inlay_glow.position = Vector3(0.0, -TRAY_DROP * 0.72, 0.0)
	root.add_child(inlay_glow)


static func _rim(root: Node3D, palette) -> void:
	## The thick outer ring: pearl body, gold band, chrome bolts, warm wash.
	var profile: Array = [
		Vector2(TRAY_RADIUS + 0.06, 0.02),
		Vector2(TRAY_RADIUS + 0.16, 0.14),
		Vector2(TRAY_RADIUS + 0.30, 0.20),
		Vector2(RADIUS - 0.12, 0.20),
		Vector2(RADIUS, 0.10),
		Vector2(RADIUS, -0.26),
		Vector2(RADIUS - 0.10, -0.40),
		Vector2(TRAY_RADIUS + 0.02, -0.44),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile, true), 64),
		palette.get_material("pearl_shell"), "Rim"))

	var band := Forms.mesh_node(
		Forms.hoop(RADIUS - 0.24, 0.10, 64, 12),
		palette.get_material("gold"), "RimBand", false)
	band.position = Vector3(0.0, 0.215, 0.0)
	root.add_child(band)

	var wash := Forms.mesh_node(
		Forms.hoop(RADIUS + 0.02, 0.048, 64, 8),
		palette.get_material("lit_gold"), "RimWash", false)
	wash.position = Vector3(0.0, -0.18, 0.0)
	root.add_child(wash)

	Forms.bolt_ring(root, palette.get_material("chrome"), 20, RADIUS - 0.55,
		0.21, 0.055, 0.045)


static func _guard(root: Node3D, palette) -> void:
	## A low aqua wall around the rim: the transparent note, kept short so it
	## never occludes the mechanism it is guarding.
	var height: float = 0.80 if palette.variant != "deck" else 0.62
	var wall: Array = [
		Vector2(RADIUS - 0.20, 0.20),
		Vector2(RADIUS - 0.17, 0.34),
		Vector2(RADIUS - 0.08, height * 0.7),
		Vector2(RADIUS, height),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(wall, Geometry.profile_normals(wall, true), 64),
		palette.get_material("acrylic_aqua"), "Guard", false))

	var edge := Forms.mesh_node(
		Forms.hoop(RADIUS, 0.045, 64, 8),
		palette.get_material("acrylic_clear"), "GuardEdge", false)
	edge.position = Vector3(0.0, height, 0.0)
	root.add_child(edge)

	# Six posts, matching the bowl's mullions so the two modules share a trim
	# language. Repetition across modules is what makes a set look designed.
	var post := Geometry.rounded_box(Vector3(0.075, height - 0.10, 0.12), 0.028, 3)
	for index in 6:
		var angle := TAU * float(index) / 6.0 + PI * 0.08
		var node := Forms.mesh_node(post, palette.get_material("silver"),
			"GuardPost%d" % index, false)
		node.position = Vector3(cos(angle) * (RADIUS - 0.14),
			0.20 + (height - 0.10) * 0.5, sin(angle) * (RADIUS - 0.14))
		node.rotation.y = -angle
		root.add_child(node)


# --- the mechanism --------------------------------------------------------

static func _mechanism(root: Node3D, palette) -> void:
	## The stepped drum and its blades, on a node that can turn.
	var housing := Forms.mesh_node(
		Forms.hub_housing(HUB_RADIUS, 1.30),
		palette.get_material("graphite_soft"), "HubHousing")
	housing.position = Vector3(0.0, 0.20, 0.0)
	root.add_child(housing)

	var crown := Forms.mesh_node(
		Geometry.rounded_disc(HUB_RADIUS * 0.66, 0.16, 0.06, 32, 3),
		palette.get_material("gold"), "HubCrown", false)
	crown.position = Vector3(0.0, 0.90, 0.0)
	root.add_child(crown)

	var pin := Forms.mesh_node(
		Geometry.rounded_disc(0.13, 0.42, 0.06, 20, 3),
		palette.get_material("chrome"), "HubPin", false)
	pin.position = Vector3(0.0, 1.10, 0.0)
	root.add_child(pin)

	var rotor := Node3D.new()
	rotor.name = "Rotor"
	rotor.position = Vector3(0.0, 0.0, 0.0)
	root.add_child(rotor)

	var blades := 5
	var length := TRAY_RADIUS - HUB_RADIUS + 0.10
	var height := 0.78
	# X is the radial reach, Y the standing height, Z the plate thickness.
	var blade_mesh := Geometry.rounded_box(Vector3(length, height, 0.13), 0.055, 4)
	var lip_mesh := Geometry.rounded_box(Vector3(length, 0.17, 0.20), 0.06, 3)
	var rib_mesh := Geometry.rounded_box(Vector3(length * 0.80, 0.26, 0.30), 0.09, 3)

	for index in blades:
		var angle := TAU * float(index) / float(blades)
		var arm := Node3D.new()
		arm.name = "Blade%d" % index
		arm.rotation.y = -angle
		rotor.add_child(arm)

		var reach := HUB_RADIUS + length * 0.5 - 0.06
		var blade := Forms.mesh_node(blade_mesh,
			palette.get_material("pearl_shell"), "Face")
		blade.position = Vector3(reach, -0.05 + height * 0.5, 0.0)
		arm.add_child(blade)

		# The leading edge, warm, and proud of the plate on the sweep side.
		var lip := Forms.mesh_node(lip_mesh,
			palette.get_material("orange_machine"), "Lip", false)
		lip.position = Vector3(reach, -0.05 + height, 0.0)
		arm.add_child(lip)

		# A dark rib along the foot: the shadow line that separates a standing
		# blade from the bright tray behind it.
		var rib := Forms.mesh_node(rib_mesh,
			palette.get_material("graphite"), "Rib")
		rib.position = Vector3(reach, 0.02, 0.0)
		arm.add_child(rib)

		var root_boss := Forms.mesh_node(
			Geometry.rounded_disc(0.16, 0.26, 0.05, 16, 2),
			palette.get_material("gold"), "Boss", false)
		root_boss.position = Vector3(HUB_RADIUS - 0.02, 0.30, 0.0)
		root_boss.rotation.z = PI * 0.5
		arm.add_child(root_boss)


static func _understructure(root: Node3D, palette) -> void:
	## The dark body the whole module stands on, and its legs.
	var drum: Array = [
		Vector2(0.0, -1.55),
		Vector2(TRAY_RADIUS * 0.52, -1.55),
		Vector2(TRAY_RADIUS * 0.60, -1.40),
		Vector2(TRAY_RADIUS * 0.60, -0.80),
		Vector2(TRAY_RADIUS * 0.86, -0.66),
		Vector2(TRAY_RADIUS * 0.86, -0.56),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(drum, Geometry.profile_normals(drum, true), 48),
		palette.get_material("graphite_deep"), "Drum"))

	var belt := Forms.mesh_node(
		Forms.hoop(TRAY_RADIUS * 0.62, 0.07, 48, 8),
		palette.get_material("gold"), "DrumBelt", false)
	belt.position = Vector3(0.0, -1.05, 0.0)
	root.add_child(belt)

	var leg_count := 6
	for index in leg_count:
		var angle := TAU * float(index) / float(leg_count) + PI * 0.15
		var top := Vector3(cos(angle) * (RADIUS - 0.55), -0.42,
			sin(angle) * (RADIUS - 0.55))
		var foot := Vector3(cos(angle) * (TRAY_RADIUS * 0.62), -1.55,
			sin(angle) * (TRAY_RADIUS * 0.62))
		root.add_child(Forms.mesh_node(
			Forms.brace(top, foot, 0.085, 8),
			palette.get_material("graphite"), "Leg%d" % index))

		var pad := Forms.mesh_node(Forms.collar(0.20, 0.11),
			palette.get_material("gold"), "LegPad%d" % index, false)
		pad.position = top + Vector3(0.0, 0.03, 0.0)
		root.add_child(pad)

	# Two motor cans on the drum: the reason the thing turns, made visible.
	for index in 2:
		var angle := PI * 0.30 + PI * float(index)
		var can := Forms.mesh_node(
			Geometry.rounded_disc(0.24, 0.52, 0.09, 24, 3),
			palette.get_material("orange_machine"), "Motor%d" % index)
		can.position = Vector3(cos(angle) * TRAY_RADIUS * 0.66, -1.05,
			sin(angle) * TRAY_RADIUS * 0.66)
		can.rotation.z = PI * 0.5
		can.rotation.y = -angle
		root.add_child(can)
