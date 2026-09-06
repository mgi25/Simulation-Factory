extends RefCounted

## STAGE 4 - THE COLLECTOR MACHINE.
##
## The module the three-stage slice never had, and the one that turns a chute
## into a machine: racers arrive from the S, circulate on a shallow pan, are
## swept by a slow rotor, and leave through one gate. It is the only place in
## the tower where something visibly *moves under power*, which is why it gets
## the machine's whole orange-and-gold actuation vocabulary and nothing else
## does.
##
##          ╭──────── low aqua guard, see-through ────────╮
##          │  ╭───── pearl rim, chrome bead, violet ───╮ │
##          │  │        ╲        ╱                      │ │
##          │  │   ─── broad paddle ───  ◉ dark hub     │ │   five blades
##          │  │        ╱        ╲                      │ │
##          │  ╰───── silver pan, one gate in the rim ──╯ │
##          ╰──── graphite drum, orange jacks, gold band ─╯
##
## ## Why a medium landmark and not a large one
##
## The brief's hierarchy puts this between the bowl and the split, and the
## reference agrees: its collector is visibly narrower than its mixing bowl.
## `HeroLayout.COLLECTOR_RADIUS` is 3.02 against the bowl's 3.72 rim, so the
## silhouette steps *in* here and back *out* at the split. A tower whose every
## disc is the same width is a stack; one that breathes in and out is a design.
##
## ## The pan is nearly flat, and that is the point
##
## A bowl drains and a collector holds. The pan falls only 0.16 across its
## whole radius, so racers sit on it in a spread rather than piling at a
## throat - which is what makes the rotor legible, because a rotor sweeping an
## empty dish is just a fan.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Layout := preload("res://assets/marble_machine/hero/hero_layout.gd")

const RADIUS := Layout.COLLECTOR_RADIUS
const PAN_RADIUS := RADIUS - 0.44
const PAN_DROP := 0.16          # the pan's fall from rim to centre
const HUB_RADIUS := 0.62
const GUARD_TOP := 0.86
const BLADES := 5
const GATE_BEARING := 20.0      # where the rim opens, in degrees
const GATE_HALF_ANGLE := 15.0


static func action_clearance() -> Dictionary:
	return {
		"shape": "cylinder",
		"centre": Vector3(0.0, 0.24, 0.0),
		"radius": PAN_RADIUS + 0.2,
		"height": GUARD_TOP + PAN_DROP + 0.5,
	}


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "CollectorHero"

	_pan(root, palette)
	_rim(root, palette)
	_guard(root, palette)
	_rotor(root, palette)
	_drum(root, palette)
	_gate(root, palette)
	return root


static func _pan_y(radius: float) -> float:
	## The pan's own surface height at a radius. A gentle cosine, so the
	## centre is lower than the edge by `PAN_DROP` and nothing in between is
	## a straight cone - a cone lights as one flat facet and kills the module.
	var t: float = clampf(radius / PAN_RADIUS, 0.0, 1.0)
	return -PAN_DROP * (0.5 + 0.5 * cos(t * PI))


static func _pan(root: Node3D, palette) -> void:
	## The polished circulating surface, plus a dark underside for it.
	var profile: Array = []
	for step in 15:
		var radius: float = PAN_RADIUS * float(step) / 14.0
		profile.append(Vector2(radius, _pan_y(radius)))
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile, false), 64),
		palette.get_material("pan_polished"), "Pan"))

	var under: Array = []
	for point in profile:
		under.append(Vector2((point as Vector2).x, (point as Vector2).y - 0.20))
	root.add_child(Forms.mesh_node(
		Geometry.lathe(under, Geometry.profile_normals(under, true), 64),
		palette.get_material("graphite"), "PanUnder"))

	# A sunk violet line just inside the rim. The mixer zone's colour reaching
	# one module further down, which is what makes the palette read as a
	# gradient rather than as seven separate paint jobs.
	var ring := Forms.mesh_node(
		Forms.hoop(PAN_RADIUS - 0.14, 0.05, 56, 8),
		palette.get_material("lit_violet_ring_hero"), "PanRing", false)
	ring.position = Vector3(0.0, _pan_y(PAN_RADIUS) - 0.055, 0.0)
	root.add_child(ring)


static func _rim(root: Node3D, palette) -> void:
	## A rolled pearl rim with a chrome bead and a gold inlay: the same
	## machined language as the bowl, one size down.
	var profile: Array = [
		Vector2(PAN_RADIUS - 0.02, -0.02),
		Vector2(PAN_RADIUS + 0.12, 0.06),
		Vector2(RADIUS - 0.20, 0.15),
		Vector2(RADIUS - 0.04, 0.10),
		Vector2(RADIUS, -0.04),
		Vector2(RADIUS - 0.06, -0.22),
		Vector2(RADIUS - 0.24, -0.30),
		Vector2(PAN_RADIUS - 0.02, -0.26),
		Vector2(PAN_RADIUS - 0.02, -0.02),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile), 64),
		palette.get_material("pearl_lip_v2"), "Rim"))

	var bead := Forms.mesh_node(
		Forms.hoop(RADIUS - 0.14, 0.042, 64, 8),
		palette.get_material("chrome"), "RimBead", false)
	bead.position = Vector3(0.0, 0.155, 0.0)
	root.add_child(bead)

	var inlay := Forms.mesh_node(
		Forms.hoop(PAN_RADIUS + 0.13, 0.045, 64, 8),
		palette.get_material("gold"), "RimInlay", false)
	inlay.position = Vector3(0.0, 0.075, 0.0)
	root.add_child(inlay)

	var edge := Forms.mesh_node(
		Forms.hoop(RADIUS - 0.01, 0.048, 64, 8),
		palette.get_material("lit_cyan_line_hero"), "RimEdge", false)
	edge.position = Vector3(0.0, -0.05, 0.0)
	root.add_child(edge)

	Forms.bolt_ring(root, palette.get_material("chrome"), 28, RADIUS - 0.14,
		0.10, 0.05, 0.045)


static func _guard(root: Node3D, palette) -> void:
	## A short transparent wall standing on the rim, and its pearl coping.
	##
	## Low on purpose - `GUARD_TOP` is 0.86 against a 0.57 racer - so the
	## marbles inside stay taller than half the wall and are never read
	## through two thicknesses of acrylic from the hero camera.
	var outer: Array = [
		Vector2(RADIUS - 0.22, 0.12),
		Vector2(RADIUS - 0.06, 0.34),
		Vector2(RADIUS + 0.06, 0.60),
		Vector2(RADIUS + 0.14, GUARD_TOP - 0.06),
	]
	root.add_child(Forms.mesh_node(
		V2Forms.shell_lathe(outer, 0.10, 64, false),
		palette.get_material("acrylic_guard"), "Guard", false))

	var coping: Array = [
		Vector2(RADIUS + 0.06, GUARD_TOP - 0.04),
		Vector2(RADIUS + 0.04, GUARD_TOP + 0.05),
		Vector2(RADIUS + 0.14, GUARD_TOP + 0.09),
		Vector2(RADIUS + 0.23, GUARD_TOP + 0.05),
		Vector2(RADIUS + 0.21, GUARD_TOP - 0.04),
		Vector2(RADIUS + 0.06, GUARD_TOP - 0.04),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(coping, Geometry.profile_normals(coping), 64),
		palette.get_material("pearl_lip_v2"), "Coping"))

	var mouth := Forms.mesh_node(
		Forms.hoop(RADIUS + 0.14, 0.042, 64, 8),
		palette.get_material("chrome"), "MouthBead", false)
	mouth.position = Vector3(0.0, GUARD_TOP + 0.09, 0.0)
	root.add_child(mouth)


static func _rotor(root: Node3D, palette) -> void:
	## The hub and its five blades, under one node so the clip can turn them.
	##
	## Five and not eight. The brief asks for four to six broad paddles and
	## the reason is legibility: at hero distance a blade is about eight
	## pixels of shell with a gold tip on it, and eight of those becomes a
	## texture. Five reads as a mechanism you could count.
	var rotor := Node3D.new()
	rotor.name = "Rotor"
	rotor.position = Vector3(0.0, _pan_y(0.0), 0.0)
	root.add_child(rotor)

	var hub := Forms.mesh_node(
		Forms.hub_housing(HUB_RADIUS, 1.30),
		palette.get_material("graphite"), "Hub")
	hub.position = Vector3(0.0, 0.50, 0.0)
	rotor.add_child(hub)

	var collar := Forms.mesh_node(
		Forms.hoop(HUB_RADIUS * 0.94, 0.07, 28, 8),
		palette.get_material("gold"), "HubCollar", false)
	collar.position = Vector3(0.0, 0.86, 0.0)
	rotor.add_child(collar)

	var cap := Forms.mesh_node(
		Geometry.rounded_disc(HUB_RADIUS * 0.55, 0.22, 0.08, 24, 3),
		palette.get_material("chrome"), "HubCap")
	cap.position = Vector3(0.0, 1.22, 0.0)
	rotor.add_child(cap)

	# The mast: what makes the hub read as driven rather than as a bollard.
	var mast := Forms.mesh_node(
		Geometry.tube([Vector3(0.0, 1.28, 0.0), Vector3(0.0, 1.92, 0.0)],
			0.085, 10),
		palette.get_material("chrome"), "Mast")
	rotor.add_child(mast)

	var beacon := Forms.mesh_node(
		Geometry.rounded_disc(0.16, 0.16, 0.06, 16, 3),
		palette.get_material("neon_violet_hero"), "Beacon", false)
	beacon.position = Vector3(0.0, 2.00, 0.0)
	rotor.add_child(beacon)

	var reach := PAN_RADIUS - 0.28
	for index in BLADES:
		var bearing := TAU * float(index) / float(BLADES)
		var direction := Vector3(cos(bearing), 0.0, sin(bearing))
		var blade := Node3D.new()
		blade.name = "Blade%d" % index
		blade.rotation.y = -bearing
		rotor.add_child(blade)

		# The paddle: a broad, thin, filleted plate, its long axis along +X,
		# tapering to a gold tip. Thin because a sweeper has to look like it
		# passes *over* the pan rather than plough it.
		var arm := Forms.mesh_node(
			Forms.paddle(reach - HUB_RADIUS * 0.6, 0.74, 0.21, 0.075),
			palette.get_material("pearl_lip_v2"), "Plate")
		arm.position = Vector3((reach + HUB_RADIUS * 0.6) * 0.5, 0.24, 0.0)
		blade.add_child(arm)

		# A graphite spine on top of the blade: the medium-scale feature that
		# stops a flat plate reading as cardboard.
		var spine := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(reach - HUB_RADIUS * 0.7, 0.16, 0.22), 0.06, 3),
			palette.get_material("graphite_soft"), "Spine")
		spine.position = Vector3((reach + HUB_RADIUS * 0.6) * 0.5, 0.38, 0.0)
		blade.add_child(spine)

		var tip := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.26, 0.34, 0.78), 0.09, 3),
			palette.get_material("gold"), "Tip")
		tip.position = Vector3(reach - 0.04, 0.26, 0.0)
		blade.add_child(tip)

		# A short lit line down the blade's leading edge: five spokes of
		# violet is what makes the rotor read at phone size.
		var lamp := Forms.mesh_node(
			Geometry.tube([
				Vector3(HUB_RADIUS * 0.8, 0.36, 0.28),
				Vector3(reach - 0.16, 0.36, 0.28)], 0.032, 8),
			palette.get_material("neon_violet_hero"), "BladeLight", false)
		blade.add_child(lamp)

		var jack := Forms.mesh_node(
			Geometry.rounded_disc(0.11, 0.26, 0.04, 14, 3),
			palette.get_material("orange_machine"), "BladeJack")
		jack.position = Vector3(HUB_RADIUS + 0.24, 0.24, 0.0)
		jack.rotation.x = PI * 0.5
		blade.add_child(jack)
	root.set_meta("rotor", rotor.get_path())


static func _drum(root: Node3D, palette) -> void:
	## The graphite housing under the pan: a stepped drum, a gold band, three
	## orange rams and a bolt ring. This is the module's whole "machine" read
	## from below, and from the hero camera it is a third of its screen area.
	var drum := Node3D.new()
	drum.name = "Drum"
	root.add_child(drum)

	var body := Forms.mesh_node(
		Forms.hub_housing(RADIUS - 0.62, 1.62),
		palette.get_material("graphite"), "Body")
	body.position = Vector3(0.0, -1.12, 0.0)
	drum.add_child(body)

	var skirt := Forms.mesh_node(
		Geometry.rounded_disc(RADIUS - 0.30, 0.26, 0.10, 48, 3),
		palette.get_material("graphite_deep"), "Skirt")
	skirt.position = Vector3(0.0, -0.44, 0.0)
	drum.add_child(skirt)

	var band := Forms.mesh_node(
		Forms.hoop(RADIUS - 0.56, 0.07, 48, 8),
		palette.get_material("gold"), "Band", false)
	band.position = Vector3(0.0, -0.90, 0.0)
	drum.add_child(band)

	var glow := Forms.mesh_node(
		Forms.hoop(RADIUS - 0.52, 0.05, 48, 8),
		palette.get_material("lit_violet"), "DrumLight", false)
	glow.position = Vector3(0.0, -1.42, 0.0)
	drum.add_child(glow)

	for index in 3:
		var bearing := deg_to_rad(52.0 + 120.0 * float(index))
		var direction := Vector3(cos(bearing), 0.0, sin(bearing))
		var ram := Forms.mesh_node(
			Geometry.rounded_disc(0.19, 1.04, 0.07, 16, 3),
			palette.get_material("orange_machine"), "Ram%d" % index)
		ram.position = direction * (RADIUS - 0.34) + Vector3(0.0, -1.00, 0.0)
		drum.add_child(ram)

		var shoe := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.52, 0.22, 0.40), 0.09, 3),
			palette.get_material("graphite_soft"), "RamShoe%d" % index)
		shoe.position = direction * (RADIUS - 0.34) + Vector3(0.0, -1.62, 0.0)
		shoe.rotation.y = -bearing
		drum.add_child(shoe)

	Forms.bolt_ring(drum, palette.get_material("chrome"), 20, RADIUS - 0.38,
		-0.32, 0.06, 0.05)


static func _gate(root: Node3D, palette) -> void:
	## The one opening in the rim, marked so the route out is not a guess.
	##
	## A machine with a closed rim is a bowl. The gate is where the collector
	## hands on to the split, and the eye has to find it in the same glance it
	## finds the rotor - so it gets a gold jamb either side, a lit sill across
	## the floor, and a short pearl lead-out apron.
	var gate := Node3D.new()
	gate.name = "Gate"
	gate.rotation.y = -deg_to_rad(GATE_BEARING)
	root.add_child(gate)

	for side in [1.0, -1.0]:
		var swing: float = deg_to_rad(GATE_HALF_ANGLE) * float(side)
		var jamb := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.22, 0.92, 0.34), 0.08, 3),
			palette.get_material("gold"),
			"Jamb%s" % ("R" if side > 0.0 else "L"))
		jamb.position = Vector3(cos(swing) * (RADIUS - 0.06), 0.36,
			sin(swing) * (RADIUS - 0.06))
		jamb.rotation.y = -swing
		gate.add_child(jamb)

	var sill := Forms.mesh_node(
		Forms.arc_hoop(RADIUS - 0.30, 0.05,
			-deg_to_rad(GATE_HALF_ANGLE), deg_to_rad(GATE_HALF_ANGLE), 12, 8),
		palette.get_material("neon_gold"), "Sill", false)
	sill.position = Vector3(0.0, 0.02, 0.0)
	gate.add_child(sill)

	# The apron: a short pearl lip carrying the floor out past the rim, so the
	# exit chute is met by geometry rather than starting in mid-air.
	var apron := Forms.mesh_node(
		Geometry.rounded_box(Vector3(0.70, 0.14, 1.30), 0.07, 3),
		palette.get_material("pearl_shell"), "Apron")
	apron.position = Vector3(RADIUS + 0.20, -0.10, 0.0)
	apron.rotation.z = -0.14
	gate.add_child(apron)
