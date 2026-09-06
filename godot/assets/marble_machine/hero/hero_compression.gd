extends RefCounted

## STAGE 6 - THE FINAL COMPRESSION.
##
## The short, dramatic connector that brings the two routes back together. Its
## whole job is a change of *rhythm*: everything above it is broad and swinging,
## and for three units of height the machine goes narrow, straight and vertical
## before opening into the arena. A frame that only ever widens has no accent
## in it; this is the accent.
##
##          blue route ╲       ╱ orange route
##                      ╲     ╱
##                   ╭───╳───╮        the merge block, gold
##                   │  ▮▮▮  │        three tightening collars
##                   │  ▮▮▮  │        and a single narrow channel
##                   ╰───┬───╯
##                       ↓             into the arena
##
## ## It is small on purpose
##
## The brief's hierarchy calls this a "small dramatic connector" and names
## making it another giant module as the failure to avoid. So it occupies ten
## per cent of the machine's height and none of its width: 3.15 units tall and
## under two wide, against a split that is eight wide directly above it. That
## contrast is the drama - not size.
##
## ## Warmth begins here
##
## This is where the palette hands over. The collars are gold rather than
## chrome, the frame masts carry warm lamps rather than cyan, and the channel's
## edge light is the finale's gold. By the time a racer reaches the arena the
## colour temperature has already changed, which is what stops the gold zone
## reading as a separate object bolted to the bottom of a blue machine.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const Layout := preload("res://assets/marble_machine/hero/hero_layout.gd")

const MERGE_SCALE := 0.72
const DROP_SCALE := 0.86

const MERGE_OPTIONS := {
	"edge_stock": 0.062,
	"bank_gain": 1.6, "bank_max": 12.0,
	"entry_flare": 0.14, "exit_flare": 0.04,
	"edge_light": "lit_gold_line", "samples": 64,
	"shell": "pearl_warm", "floor": "running_polished",
	"keel": "graphite_deep", "guard": "acrylic_gold",
	"scale": MERGE_SCALE, "ribs": false,
}

const DROP_OPTIONS := {
	"edge_stock": 0.062,
	"bank_gain": 2.0, "bank_max": 16.0,
	"entry_flare": 0.30, "exit_flare": 0.04,
	"edge_light": "lit_gold_line", "samples": 72,
	"shell": "pearl_warm", "floor": "running_warm",
	"keel": "graphite_deep", "guard": "acrylic_gold",
	"scale": DROP_SCALE,
}


static func merge_block(palette) -> Node3D:
	## Where the two branches become one: a gold-banded junction housing.
	##
	## Built as a wedge that is wide at the top and narrow at the bottom, so
	## the shape itself performs the compression. Two mouths in, one out.
	var root := Node3D.new()
	root.name = "MergeBlock"
	root.position = Vector3(0.00, 4.98, 0.58)

	var body := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.72, 0.76, 1.14), 0.22, 4),
		palette.get_material("pearl_warm"), "Body")
	root.add_child(body)

	var waist := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.02, 0.46, 0.90), 0.16, 4),
		palette.get_material("graphite"), "Waist")
	waist.position = Vector3(0.0, -0.62, 0.0)
	root.add_child(waist)

	var band := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.84, 0.09, 1.26), 0.04, 2),
		palette.get_material("gold"), "Band", false)
	band.position = Vector3(0.0, 0.36, 0.0)
	root.add_child(band)

	var glow := Forms.mesh_node(
		Geometry.tube([Vector3(-0.82, 0.08, 0.56), Vector3(0.82, 0.08, 0.56)],
			0.034, 8),
		palette.get_material("neon_gold"), "Glow", false)
	root.add_child(glow)

	for side in [1.0, -1.0]:
		var boss := Forms.mesh_node(
			Geometry.rounded_disc(0.22, 0.20, 0.07, 18, 3),
			palette.get_material("gold_dark"),
			"Boss%s" % ("R" if side > 0.0 else "L"))
		boss.position = Vector3(side * 0.84, 0.0, 0.0)
		boss.rotation.z = PI * 0.5
		root.add_child(boss)

		var ram := Forms.mesh_node(
			Geometry.rounded_disc(0.13, 0.52, 0.05, 14, 3),
			palette.get_material("orange_machine"),
			"Ram%s" % ("R" if side > 0.0 else "L"))
		ram.position = Vector3(side * 0.62, -0.48, 0.28)
		root.add_child(ram)

	Forms.bolt_ring(root, palette.get_material("chrome"), 12, 0.72, 0.38,
		0.045, 0.04)
	return root


static func collars(palette, path: Array) -> Node3D:
	## Three tightening rings down the drop channel.
	##
	## Each one smaller than the last. A channel of constant width with rings
	## on it is decorated; a channel whose rings *close* down its length reads
	## as being squeezed, and that is the module's only idea.
	var root := Node3D.new()
	root.name = "Collars"
	if path.size() < 2:
		return root

	# The fourth ring is at the very mouth. A swept channel closes with a
	# flat cap normal to its own tangent, and this one points down and
	# forward - straight at the hero camera - so without a fitting over it
	# the compression ends in a pale wedge hanging above the arena.
	var steps := [[0.14, 0.86], [0.46, 0.74], [0.78, 0.63], [1.0, 0.56]]
	for index in steps.size():
		var entry: Array = steps[index]
		var t: float = entry[0]
		var radius: float = entry[1]
		var at: Vector3 = Forms.sample_at(path, t)
		var pivot := Node3D.new()
		pivot.name = "Collar%d" % index
		pivot.position = at
		root.add_child(pivot)

		pivot.add_child(Forms.mesh_node(
			Forms.hoop(radius, 0.085, 26, 8),
			palette.get_material("gold"), "Ring"))
		var lit := Forms.mesh_node(
			Forms.hoop(radius - 0.10, 0.042, 26, 8),
			palette.get_material("neon_gold"), "RingLight", false)
		lit.position = Vector3(0.0, 0.02, 0.0)
		pivot.add_child(lit)

		for side in [1.0, -1.0]:
			var lug := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.20, 0.16, 0.24), 0.05, 3),
				palette.get_material("graphite_soft"),
				"Lug%s" % ("R" if side > 0.0 else "L"))
			lug.position = Vector3(side * radius, 0.0, 0.0)
			pivot.add_child(lug)
	return root


static func frame(palette) -> Node3D:
	## Two masts flanking the compression, with warm lamps on them.
	##
	## The brief asks for strong framing supports here, and framing is meant
	## literally: two verticals either side of the narrowest part of the
	## machine make the narrowness visible. They sit outboard at x = +/-2.5 and
	## behind at z = -0.6, so neither one crosses the channel.
	var root := Node3D.new()
	root.name = "CompressionFrame"

	for side in [1.0, -1.0]:
		var suffix := "R" if side > 0.0 else "L"
		var pivot := Node3D.new()
		pivot.name = "Mast%s" % suffix
		pivot.position = Vector3(side * 2.52, 0.0, -0.62)
		root.add_child(pivot)

		var top := Layout.COMPRESSION_TOP_Y + 0.90
		var base := Layout.FINISH_Y + 0.60
		var mid := (top + base) * 0.5

		var shaft := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.34, top - base, 0.40), 0.12, 4),
			palette.get_material("graphite"), "Shaft")
		shaft.position = Vector3(0.0, mid, 0.0)
		pivot.add_child(shaft)

		var cap := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.50, 0.22, 0.54), 0.09, 3),
			palette.get_material("gold_dark"), "Cap")
		cap.position = Vector3(0.0, top, 0.0)
		pivot.add_child(cap)

		var lamp := Forms.mesh_node(
			Geometry.tube([Vector3(0.0, base + 0.30, 0.22),
				Vector3(0.0, top - 0.30, 0.22)], 0.032, 8),
			palette.get_material("lit_gold_line"), "Lamp", false)
		pivot.add_child(lamp)

		# A short arm reaching in toward the channel, ending in a collar. It
		# is what makes the masts read as holding the compression rather than
		# as standing beside it.
		var arm := Forms.mesh_node(
			Geometry.rounded_box(Vector3(1.30, 0.24, 0.28), 0.09, 3),
			palette.get_material("graphite_soft"), "Arm")
		arm.position = Vector3(-side * 0.78, Layout.COMPRESSION_BOTTOM_Y + 0.85,
			0.30)
		arm.rotation.z = side * 0.16
		pivot.add_child(arm)

		var boss := Forms.mesh_node(
			Geometry.rounded_disc(0.17, 0.18, 0.06, 16, 3),
			palette.get_material("gold"), "ArmBoss")
		boss.position = Vector3(-side * 1.36, Layout.COMPRESSION_BOTTOM_Y + 0.94,
			0.30)
		boss.rotation.z = PI * 0.5
		pivot.add_child(boss)
	return root
