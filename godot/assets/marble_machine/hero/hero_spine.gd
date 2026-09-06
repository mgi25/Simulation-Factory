extends RefCounted

## THE SUPPORT FRAME - two slim towers, a narrow trunk, and air.
##
## The V2.2 machine was built against a solid back slab. It worked: the modules
## had something to be read against. It also cost the frame its depth - at 1.15
## times the pylon spacing there was no gap between the wall and the towers, and
## the gorge could not be seen *through* the machine at any height. The brief's
## instruction is to redesign it, and the redesign is subtractive.
##
##      ║                    ║        two towers, half as thick as V2's
##      ║   ╔══╗  module  ╔══╗ ║       and pushed outboard past every rim
##      ║   ║  ║          ║  ║ ║
##      ║╲ ╱║ trunk (narrow) ║╲ ╱║     open X braces at four levels only
##      ║ ╳ ║  ╚══╝  ╚══╝  ║ ╳ ║      sky visible between every piece
##      ║╱ ╲║                ║╱ ╲║
##
## Three parts and nothing else:
##
##   1. TOWER   a slim moulded column, 0.68 across against V2's 1.04
##   2. TRUNK   a stack of narrow drums behind the upper modules only
##   3. YOKE    an open X brace, at four levels chosen to miss every module
##
## ## The trunk stops at the collector
##
## Above the collector the modules are round and centred and there is a real
## hole behind them; the trunk fills it, which is the job the back wall used to
## do. Below the collector the split is eight units wide and full of its own
## structure, so a trunk there would be hidden by the branches and would only
## close the one part of the frame that most needs air in it. It runs from 13.8
## to 27.6 and stops.
##
## ## Nothing crosses the action
##
## The towers sit at x = +/-3.94, outboard of the bowl's 3.72 rim and the
## finish arena's own guard, and at z = -3.05, behind every module centre. The
## yokes are at 4.40, 14.10, 22.20 and 28.60 - between the finish and the
## compression, between the split and the collector, between the S and the
## bowl, and above the start. Every one of them falls in a gap.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const Layout := preload("res://assets/marble_machine/hero/hero_layout.gd")

const PANEL_LEVELS := [3.10, 28.60]


static func towers(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "Towers"
	for side in [1.0, -1.0]:
		var tower := _tower(palette)
		tower.name = "Tower%s" % ("R" if side > 0.0 else "L")
		tower.position = Vector3(side * Layout.TOWER_X, 0.0, Layout.TOWER_Z)
		root.add_child(tower)
	return root


static func _tower(palette) -> Node3D:
	## One column: a slim shaft, a proud face rib and a lit channel.
	##
	## Deliberately featureless compared with what it was. With a panel break
	## and a gold trim at every module level, plus a bracket arm at each, the
	## right-hand tower read as a ladder standing beside the machine - and a
	## ladder at the frame edge is the loudest thing in the picture. The
	## breaks are down to two, at the top and the bottom, and the tower now
	## sits at z = -6.3 where the core is the thing the eye finds first.
	var node := Node3D.new()
	var base := Layout.TOWER_BASE
	var top := Layout.TOWER_TOP
	var height := top - base
	var mid := (top + base) * 0.5
	var half := Layout.TOWER_HALF

	# `graphite_soft` rather than `graphite`, and eight and a half units
	# behind the machine's centre. A near-black column at the frame's edge is
	# the loudest line in the picture whatever its width, and the fix is
	# value and depth rather than thickness: one step lighter and one step
	# further back, the tower reads as the structure *behind* the machine
	# instead of a bar standing beside it.
	var shaft := Forms.mesh_node(
		Geometry.rounded_box(Vector3(half * 2.0, height, half * 1.70), 0.12, 4),
		palette.get_material("graphite_soft"), "Shaft")
	shaft.position = Vector3(0.0, mid, 0.0)
	node.add_child(shaft)

	var rib := Forms.mesh_node(
		Geometry.rounded_box(
			Vector3(half * 1.05, height - 0.9, half * 0.55), 0.08, 3),
		palette.get_material("graphite"), "FaceRib")
	rib.position = Vector3(0.0, mid, half * 1.00)
	node.add_child(rib)

	# The lit channel runs the whole height and is the single longest line in
	# the frame. It is what gives the machine a vertical read from a distance
	# at which no individual module is yet legible.
	node.add_child(Forms.mesh_node(
		Geometry.tube([
			Vector3(0.0, base + 0.7, half * 0.94),
			Vector3(0.0, top - 0.8, half * 0.94)], 0.030, 8),
		palette.get_material("lit_cyan_line_hero"), "Channel", false))

	for index in PANEL_LEVELS.size():
		var y: float = float(PANEL_LEVELS[index])
		var band := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(half * 2.34, 0.26, half * 2.00), 0.08, 3),
			palette.get_material("graphite_soft"), "Break%d" % index)
		band.position = Vector3(0.0, y, 0.0)
		node.add_child(band)

		var trim := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(half * 2.40, 0.05, half * 2.06), 0.02, 2),
			palette.get_material("gold"), "BreakTrim%d" % index, false)
		trim.position = Vector3(0.0, y + 0.15, 0.0)
		node.add_child(trim)

	var cap := Forms.mesh_node(
		Geometry.rounded_box(Vector3(half * 2.6, 0.34, half * 2.2), 0.10, 3),
		palette.get_material("graphite_deep"), "Cap")
	cap.position = Vector3(0.0, top, 0.0)
	node.add_child(cap)

	var beacon := Forms.mesh_node(
		Geometry.rounded_disc(0.11, 0.14, 0.05, 12, 3),
		palette.get_material("neon_cyan"), "Beacon", false)
	beacon.position = Vector3(0.0, top + 0.26, 0.0)
	node.add_child(beacon)

	var foot := Forms.mesh_node(
		Geometry.rounded_box(Vector3(half * 3.0, 0.46, half * 2.7), 0.13, 4),
		palette.get_material("graphite_deep"), "Foot")
	foot.position = Vector3(0.0, base + 0.18, 0.0)
	node.add_child(foot)
	return node


static func trunk(palette) -> Node3D:
	## The dark core the modules are threaded onto.
	##
	## The concept's tower is not a stack of discs in mid-air - there is a
	## continuous dark trunk behind it, and every gap between two modules is
	## filled by that trunk rather than by background. Reading the two side by
	## side, it is the single largest structural difference, and the reason
	## the first assembled build looked sparse where the concept looks dense.
	##
	## Built as one drum per gap, from `Layout.CORE_SEGMENTS`, each sized for
	## the gap it fills and stopping clear of the module envelopes either
	## side. Segmented rather than continuous because a segment can be
	## *absent* where a module is transparent: a core seen through the bowl's
	## glass is a black post standing in the middle of the machine's first
	## hero module.
	##
	## Each drum carries the same four features - a gold waist band, a lit
	## ring, four shallow louvres and one orange service block - so the core
	## reads as one continuous piece of engineering seen in sections rather
	## than as seven unrelated cylinders.
	var root := Node3D.new()
	root.name = "Trunk"

	for index in Layout.CORE_SEGMENTS.size():
		var entry: Array = Layout.CORE_SEGMENTS[index]
		var y: float = entry[0]
		var height: float = entry[1]
		var radius: float = entry[2]
		var z: float = entry[3]

		var drum := Forms.mesh_node(
			Forms.hub_housing(radius, height),
			palette.get_material("graphite"), "Drum%d" % index)
		drum.position = Vector3(0.0, y, z)
		root.add_child(drum)

		var band := Forms.mesh_node(
			Forms.hoop(radius * 1.04, 0.075, 30, 8),
			palette.get_material("gold"), "Band%d" % index, false)
		band.position = Vector3(0.0, y + height * 0.40, z)
		root.add_child(band)

		# Alternating, and never the full-energy neon key: three violet
		# rings stacked behind the S read as a lava lamp rather than as a
		# machine, and the core's job is to be a dark backdrop with detail
		# in it, not a light source.
		var glow := Forms.mesh_node(
			Forms.hoop(radius * 0.98, 0.045, 30, 8),
			palette.get_material("lit_violet" if index % 2 == 0
				else "lit_cyan"), "Ring%d" % index, false)
		glow.position = Vector3(0.0, y - height * 0.34, z)
		root.add_child(glow)

		# Louvres on the front face: a big dark cylinder needs a direction as
		# well as a value, and four shallow uprights give it one without
		# adding a silhouette edge.
		for step in 4:
			var offset: float = (float(step) - 1.5) * radius * 0.42
			var fin := Forms.mesh_node(
				Geometry.rounded_box(
					Vector3(radius * 0.16, height * 0.62, radius * 0.16),
					radius * 0.06, 3),
				palette.get_material("graphite_deep"),
				"Louvre%d_%d" % [index, step])
			fin.position = Vector3(offset, y, z + radius * 0.88)
			root.add_child(fin)

		var lamp := Forms.mesh_node(
			Geometry.tube([
				Vector3(-radius * 0.66, y + height * 0.22, z + radius * 0.94),
				Vector3(radius * 0.66, y + height * 0.22, z + radius * 0.94)],
				0.028, 8),
			palette.get_material("lit_cyan"), "Lamp%d" % index, false)
		root.add_child(lamp)

		var block := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.46, 0.36, 0.32), 0.10, 3),
			palette.get_material("orange_machine"), "Service%d" % index)
		block.position = Vector3(
			(1.0 if index % 2 == 0 else -1.0) * (radius + 0.12),
			y - height * 0.14, z + 0.34)
		root.add_child(block)

		Forms.bolt_ring(root, palette.get_material("chrome"), 12,
			radius * 0.86, y + height * 0.48, 0.045, 0.04)
	return root


static func service_rings(palette) -> Node3D:
	## Narrow lit walkway rings around the core, at three heights.
	##
	## The last of the density the concept has and the first build did not.
	## Its tower carries a service ring at every level where two modules meet
	## - a thin dark deck with a lit kerb and a rail - and those rings are
	## most of what makes the gaps between its discs read as *machine* rather
	## than as air. Three of them here, sited between modules and inside every
	## module's plan radius, so none can cross an action volume.
	var root := Node3D.new()
	root.name = "ServiceRings"

	for entry in [[22.35, 2.30, -1.25], [16.05, 2.05, -1.25],
			[12.95, 1.85, -1.10]]:
		var y: float = entry[0]
		var radius: float = entry[1]
		var z: float = entry[2]
		var node := Node3D.new()
		node.name = "Ring%d" % int(y)
		node.position = Vector3(0.0, y, z)
		root.add_child(node)

		var deck: Array = [
			Vector2(radius - 0.42, -0.09),
			Vector2(radius, -0.09),
			Vector2(radius, 0.05),
			Vector2(radius - 0.42, 0.05),
			Vector2(radius - 0.42, -0.09),
		]
		node.add_child(Forms.mesh_node(
			Geometry.lathe(deck, Geometry.profile_normals(deck), 44),
			palette.get_material("graphite_soft"), "Deck"))

		var kerb := Forms.mesh_node(
			Forms.hoop(radius, 0.05, 44, 8),
			palette.get_material("gold"), "Kerb", false)
		kerb.position = Vector3(0.0, 0.07, 0.0)
		node.add_child(kerb)

		var lit := Forms.mesh_node(
			Forms.hoop(radius - 0.40, 0.035, 40, 8),
			palette.get_material("lit_cyan"), "Lamp", false)
		lit.position = Vector3(0.0, 0.07, 0.0)
		node.add_child(lit)

		# A handrail on eight stanchions: thin, regular, and the one thing
		# that gives a ring a *height* instead of being a painted line.
		var rail := Forms.mesh_node(
			Forms.hoop(radius - 0.10, 0.030, 44, 6),
			palette.get_material("silver"), "Rail", false)
		rail.position = Vector3(0.0, 0.40, 0.0)
		node.add_child(rail)
		for step in 8:
			var bearing := TAU * float(step) / 8.0
			node.add_child(Forms.mesh_node(
				Geometry.tube([
					Vector3(cos(bearing) * (radius - 0.10), 0.02,
						sin(bearing) * (radius - 0.10)),
					Vector3(cos(bearing) * (radius - 0.10), 0.40,
						sin(bearing) * (radius - 0.10))], 0.026, 6),
				palette.get_material("silver"), "Post%d" % step, false))

		# Two small orange units per ring, on opposite bearings.
		for step in 2:
			var bearing := deg_to_rad(48.0 + 180.0 * float(step))
			var unit := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.40, 0.30, 0.30), 0.09, 3),
				palette.get_material("orange_machine"), "Unit%d" % step)
			unit.position = Vector3(cos(bearing) * (radius - 0.24), 0.19,
				sin(bearing) * (radius - 0.24))
			unit.rotation.y = -bearing
			node.add_child(unit)
	return root


static func yokes(palette) -> Node3D:
	## Four open X braces tying the towers together.
	##
	## An X and not a beam. A horizontal beam at four levels reads as four
	## more lines across a picture that already has plenty; an X has a hole in
	## the middle of it, and at this distance the hole is what the eye
	## registers. Two diagonals plus a light beam is three pieces of stock per
	## level and the environment shows through all of them.
	var root := Node3D.new()
	root.name = "Yokes"
	var span := Layout.TOWER_X - 0.20
	var z := Layout.TOWER_Z

	for index in Layout.YOKE_LEVELS.size():
		var y: float = float(Layout.YOKE_LEVELS[index])
		var node := Node3D.new()
		node.name = "Yoke%d" % index
		root.add_child(node)

		var beam := Forms.mesh_node(
			Geometry.rounded_box(Vector3(span * 2.0, 0.28, 0.36), 0.11, 4),
			palette.get_material("graphite_soft"), "Beam")
		beam.position = Vector3(0.0, y, z)
		node.add_child(beam)

		var drop: float = 1.20 * (1.0 if index % 2 == 0 else -1.0)
		node.add_child(Forms.mesh_node(
			Geometry.tube([
				Vector3(-span, y, z + 0.10),
				Vector3(span, y - drop, z + 0.10)], 0.058, 8),
			palette.get_material("graphite"), "Diagonal"))

		var lit := Forms.mesh_node(
			Geometry.tube([
				Vector3(-span * 0.86, y + 0.17, z + 0.20),
				Vector3(span * 0.86, y + 0.17, z + 0.20)], 0.026, 8),
			palette.get_material("lit_cyan"), "Lamp", false)
		node.add_child(lit)

		for side in [1.0, -1.0]:
			var collar := Forms.mesh_node(
				Geometry.rounded_disc(0.24, 0.18, 0.07, 18, 3),
				palette.get_material("gold"),
				"Collar%s" % ("R" if side > 0.0 else "L"), false)
			collar.position = Vector3(side * (span - 0.16), y, z)
			collar.rotation.z = PI * 0.5
			node.add_child(collar)
	return root


static func cantilever(palette, from_side: float, y: float, reach: Vector3,
		node_name: String) -> Node3D:
	## A bracket from one tower out to a module. A tapered wedge, a gold
	## collar where it leaves the tower, and a small orange jack under it.
	var node := Node3D.new()
	node.name = node_name
	var root_at := Vector3(from_side * Layout.TOWER_X, y, Layout.TOWER_Z)
	var span := reach - root_at
	var length := span.length()
	var mid := root_at + span * 0.5

	var arm := Forms.mesh_node(
		Geometry.rounded_box(Vector3(length, 0.34, 0.40), 0.13, 4),
		palette.get_material("graphite"), "Arm")
	arm.position = mid
	arm.rotation.y = atan2(-span.z, span.x)
	arm.rotation.z = asin(clampf(span.y / maxf(length, 0.001), -1.0, 1.0))
	node.add_child(arm)

	var collar := Forms.mesh_node(
		Geometry.rounded_disc(0.26, 0.22, 0.08, 18, 3),
		palette.get_material("gold"), "Collar")
	collar.position = root_at + span.normalized() * 0.26
	collar.rotation.z = PI * 0.5
	collar.rotation.y = atan2(-span.z, span.x)
	node.add_child(collar)

	var jack := Forms.mesh_node(
		Geometry.rounded_disc(0.12, 0.32, 0.05, 14, 3),
		palette.get_material("orange_machine"), "Jack")
	jack.position = mid + Vector3(0.0, -0.28, 0.0)
	jack.rotation.z = PI * 0.5
	jack.rotation.y = atan2(-span.z, span.x)
	node.add_child(jack)
	return node


static func saddle(palette, at: Vector3, heading: float,
		node_name: String) -> Node3D:
	## The small cradle a track keel rests in where it crosses a support.
	var node := Node3D.new()
	node.name = node_name
	node.position = at
	node.rotation.y = heading

	node.add_child(Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.52, 0.30, 0.62), 0.12, 4),
		palette.get_material("graphite_soft"), "Bed"))
	for side in [1.0, -1.0]:
		var cheek := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.20, 0.46, 0.58), 0.08, 3),
			palette.get_material("graphite"),
			"Cheek%s" % ("R" if side > 0.0 else "L"))
		cheek.position = Vector3(side * 0.74, 0.20, 0.0)
		node.add_child(cheek)
		var bolt := Forms.mesh_node(
			Geometry.rounded_disc(0.10, 0.09, 0.035, 12, 2),
			palette.get_material("gold"),
			"SaddleBolt%s" % ("R" if side > 0.0 else "L"), false)
		bolt.position = Vector3(side * 0.74, 0.30, 0.32)
		bolt.rotation.x = PI * 0.5
		node.add_child(bolt)
	return node


static func plinth(palette) -> Node3D:
	## The base the tower stands on. Narrower than the arena above it.
	##
	## Deliberately smaller than the V2 plinth and smaller than the finish
	## arena's own radius, so the widest thing at the bottom of the frame is
	## the *arena* and not a slab under it. A base that out-measures the
	## module it carries takes the eye off the finish, which at the bottom of
	## a thirty-unit tower is the last place it should be looking.
	var node := Node3D.new()
	node.name = "Plinth"
	node.position = Vector3(0.0, Layout.PLINTH_Y, 0.0)

	node.add_child(Forms.mesh_node(
		Geometry.rounded_disc(3.05, 0.52, 0.18, 48, 4),
		palette.get_material("graphite_deep"), "Lower"))

	var upper := Forms.mesh_node(
		Geometry.rounded_disc(2.42, 0.36, 0.13, 48, 4),
		palette.get_material("graphite"), "Upper")
	upper.position = Vector3(0.0, 0.40, 0.0)
	node.add_child(upper)

	var inlay := Forms.mesh_node(
		Forms.hoop(2.16, 0.055, 48, 8), palette.get_material("gold"),
		"Inlay", false)
	inlay.position = Vector3(0.0, 0.58, 0.0)
	node.add_child(inlay)

	var edge := Forms.mesh_node(
		Forms.hoop(3.03, 0.055, 56, 8),
		palette.get_material("lit_gold_wash"), "EdgeLight", false)
	edge.position = Vector3(0.0, 0.18, 0.0)
	node.add_child(edge)

	Forms.bolt_ring(node, palette.get_material("chrome"), 20, 2.76, 0.26,
		0.07, 0.06)

	for index in 3:
		var bearing := deg_to_rad(60.0 + 120.0 * float(index))
		var direction := Vector3(cos(bearing), 0.0, sin(bearing))
		var block := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.62, 0.34, 0.46), 0.11, 3),
			palette.get_material("orange_machine"), "Service%d" % index)
		block.position = direction * 2.62 + Vector3(0.0, 0.44, 0.0)
		block.rotation.y = -bearing
		node.add_child(block)
	return node
