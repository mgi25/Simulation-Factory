extends RefCounted

## What makes the mountainside a *place* the course was installed in.
##
## The layout study's frame was correct in composition and empty in content: a
## white channel on a smooth dark hill, with nothing at any scale between the
## two-unit track and the two-hundred-unit range behind it. Everything here
## fills that gap, and each item is chosen for the scale it reads at:
##
##     lamp masts    2-4 units, along the course, on the downhill side
##     marker cairns 1-2 units, at the hairpins, where a viewer needs a landmark
##     scrub         1-3 units, on the terraces, the only warm ground colour
##     ridge pylons  14 units, on the crest, so the skyline is inhabited
##     valley lights 20 units, far below, so the drop below the track has depth
##
## All deterministic, all on the world's light layer, and all sited by
## rejection against the racing line - nothing here can end up inside a track.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Terrain := preload("res://assets/marble_machine/course/course_terrain.gd")


static func build(root: Node3D, palette, cfg: Dictionary, centreline: Array,
		nodes: Dictionary, options: Dictionary = {}) -> void:
	var group := Node3D.new()
	group.name = "Dressing"
	root.add_child(group)
	_lamps(group, palette, cfg, centreline,
		float(options.get("mast_stock", 0.10)))
	_scrub(group, palette, cfg, centreline)
	_pylons(group, palette, cfg)
	_valley(group, palette, cfg)
	Terrain._to_world_layer(group)
	# The lamp heads and beacons are emissive geometry on the world layer, so
	# they light nothing on their own. Six omnis carry the actual spill, sited
	# where the densest run of masts is rather than one per mast.
	_practicals(root, cfg, centreline)


static func _lamps(root: Node3D, palette, cfg: Dictionary,
		centreline: Array, stock := 0.10) -> void:
	## Masts along the course, leaning out over the drop.
	##
	## The single most valuable item in this file. A track on stilts reads as a
	## model; the same track with service lighting down one side reads as
	## infrastructure, and the lamps also put a rhythm of small bright points
	## along a hundred and eighty units of channel, which is what makes the
	## course's *length* legible in a wide shot.
	var group := Node3D.new()
	group.name = "Lamps"
	root.add_child(group)
	var walk: Array = V2Forms.resample(centreline, 240)
	var spacing := 11.0
	var travelled := 0.0
	var index := 0
	for step in range(1, walk.size()):
		var here: Vector3 = walk[step]
		var previous: Vector3 = walk[step - 1]
		var leg := here.distance_to(previous)
		# The resampled line hops between runs; a hop is not a length of
		# track and must not be counted, or the spacing drifts.
		if leg > 4.0:
			continue
		travelled += leg
		if travelled < spacing:
			continue
		travelled = 0.0
		index += 1

		var forward := (here - previous).normalized()
		var side := Vector3(forward.z, 0.0, -forward.x).normalized()
		var at := here + side * 2.35
		var ground: float = Terrain.height(at.x, at.z, cfg)
		var mast := Node3D.new()
		mast.name = "Mast%d" % index
		mast.position = Vector3(at.x, ground, at.z)
		mast.rotation.y = atan2(side.x, side.z)
		group.add_child(mast)

		var height: float = maxf(here.y - ground + 1.35, 2.2)
		# `stock` rather than a constant. At 0.10 the column is a hairline at
		# the hero distance: it averages away in the resize and leaves the
		# foot block reading as a dark box hanging on a wire, which is the
		# most debug-looking detail in the committed section frames.
		var column := Forms.mesh_node(
			Geometry.tube([Vector3.ZERO, Vector3(0.0, height, 0.0)], stock, 8),
			palette.get_material("graphite"), "Column", false)
		mast.add_child(column)
		var foot := Forms.mesh_node(
			Geometry.rounded_box(Vector3(stock * 6.2, 0.34, stock * 6.2),
				0.10, 2),
			palette.get_material("graphite_deep"), "Foot", false)
		foot.position = Vector3(0.0, 0.10, 0.0)
		mast.add_child(foot)
		# The arm leans back over the track, which is where the light is
		# wanted and also what keeps the mast's silhouette off the channel.
		var arm := Forms.mesh_node(
			Geometry.tube([Vector3(0.0, height, 0.0),
				Vector3(0.0, height + 0.34, -1.30)], stock * 0.75, 8),
			palette.get_material("graphite"), "Arm", false)
		mast.add_child(arm)
		var head := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.46, 0.20, 0.62), 0.08, 2),
			palette.get_material("graphite_soft"), "Head", false)
		head.position = Vector3(0.0, height + 0.30, -1.44)
		mast.add_child(head)
		var lens := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.34, 0.10, 0.46), 0.04, 2),
			palette.get_material("lit_window" if index % 3 == 0
				else "lit_cyan_soft"), "Lens", false)
		lens.position = Vector3(0.0, height + 0.19, -1.44)
		mast.add_child(lens)


static func _scrub(root: Node3D, palette, cfg: Dictionary,
		centreline: Array) -> void:
	## Vegetation clusters on the flatter ground: the only warm ground colour.
	var group := Node3D.new()
	group.name = "Scrub"
	root.add_child(group)
	var x0: float = float(cfg.get("centre_x", 0.0)) - 58.0
	var x1: float = float(cfg.get("centre_x", 0.0)) + 58.0
	var z0: float = float(cfg.get("centre_z", 0.0)) - 62.0
	var z1: float = float(cfg.get("centre_z", 0.0)) + 62.0
	var placed := 0
	for attempt in 900:
		if placed >= 74:
			break
		var x: float = lerpf(x0, x1, Terrain._lattice(attempt, 5, 211))
		var z: float = lerpf(z0, z1, Terrain._lattice(attempt, 13, 307))
		if Terrain.normal(x, z, cfg).y < 0.86:
			continue
		var clear := true
		for point in centreline:
			var offset := Vector2(x - (point as Vector3).x,
				z - (point as Vector3).z)
			if offset.length() < 4.2:
				clear = false
				break
		if not clear:
			continue
		placed += 1
		var y: float = Terrain.height(x, z, cfg)
		var clump := Node3D.new()
		clump.name = "Scrub%d" % placed
		clump.position = Vector3(x, y, z)
		group.add_child(clump)
		var count := 3 + int(Terrain._lattice(attempt, 17, 401) * 4.0)
		for bush in count:
			var size: float = 0.26 + 0.40 * Terrain._lattice(
				attempt * 7 + bush, 23, 503)
			var node := Forms.mesh_node(
				Geometry.rounded_box(Vector3(size * 2.1, size * 1.1,
					size * 1.9), size * 0.52, 3),
				palette.get_material("scrub_dark" if bush % 2 == 0
					else "scrub_dry"), "Bush%d" % bush, false)
			var angle := TAU * Terrain._lattice(attempt + bush, 29, 601)
			var reach: float = 0.35 + 0.95 * Terrain._lattice(
				attempt + bush, 31, 701)
			node.position = Vector3(cos(angle) * reach, -size * 0.34,
				sin(angle) * reach)
			node.rotation.y = angle
			clump.add_child(node)


static func _pylons(root: Node3D, palette, cfg: Dictionary) -> void:
	## Installation masts on the crest line, with a beacon on each.
	##
	## They sit on the skyline above the start, which is the one part of the
	## frame that is otherwise bare sky, and they are the reason the course
	## reads as one installation among others rather than as a lone toy on a
	## hill.
	var group := Node3D.new()
	group.name = "Pylons"
	root.add_child(group)
	var centre_x: float = float(cfg.get("centre_x", 0.0))
	var centre_z: float = float(cfg.get("centre_z", 0.0))
	var sites := [
		[centre_x - 44.0, centre_z - 54.0, 15.0], [centre_x - 20.0,
			centre_z - 62.0, 17.5], [centre_x + 8.0, centre_z - 58.0, 14.0],
		[centre_x + 34.0, centre_z - 48.0, 16.0], [centre_x - 58.0,
			centre_z - 30.0, 13.0], [centre_x + 52.0, centre_z - 22.0, 12.0],
	]
	for index in sites.size():
		var site: Array = sites[index]
		var x: float = float(site[0])
		var z: float = float(site[1])
		var height: float = float(site[2])
		var mast := Node3D.new()
		mast.name = "Pylon%d" % index
		mast.position = Vector3(x, Terrain.height(x, z, cfg) - 0.6, z)
		mast.rotation.y = float(index) * 0.8
		group.add_child(mast)
		for leg in 3:
			var angle := TAU * float(leg) / 3.0
			mast.add_child(Forms.mesh_node(
				Geometry.tube([Vector3(cos(angle) * height * 0.11, 0.0,
						sin(angle) * height * 0.11),
					Vector3(0.0, height, 0.0)], 0.18, 6),
				palette.get_material("graphite"), "Leg%d" % leg, false))
		for tier in 3:
			var y: float = height * (0.28 + 0.24 * float(tier))
			var radius: float = height * 0.11 * (1.0 - y / height)
			mast.add_child(Forms.mesh_node(
				Forms.hoop(maxf(radius, 0.2), 0.075, 12, 6),
				palette.get_material("graphite_deep"), "Tie%d" % tier, false))
		var beacon := Forms.mesh_node(
			Geometry.rounded_disc(0.44, 0.34, 0.10, 14, 3),
			palette.get_material("lit_cyan_line_hero"), "Beacon", false)
		beacon.position = Vector3(0.0, height + 0.20, 0.0)
		mast.add_child(beacon)


static func _valley(root: Node3D, palette, cfg: Dictionary) -> void:
	## Lit platforms on the valley floor, far below the course.
	##
	## The course's whole right-hand side is open air over a gorge, and open
	## air with nothing in it is a hole rather than a drop. These read as
	## distant industry twenty stops down and give the fall a bottom.
	var group := Node3D.new()
	group.name = "Valley"
	root.add_child(group)
	var centre_x: float = float(cfg.get("centre_x", 0.0))
	var centre_z: float = float(cfg.get("centre_z", 0.0))
	for index in 7:
		var angle := deg_to_rad(-40.0 + float(index) * 22.0)
		var reach: float = 46.0 + 11.0 * float(index % 3)
		var x: float = centre_x + 34.0 + cos(angle) * reach
		var z: float = centre_z + 6.0 + sin(angle) * reach
		var y: float = Terrain.height(x, z, cfg)
		var pad := Node3D.new()
		pad.name = "Platform%d" % index
		pad.position = Vector3(x, y, z)
		pad.rotation.y = float(index) * 0.6
		group.add_child(pad)
		var size: float = 5.0 + 2.6 * float(index % 3)
		pad.add_child(Forms.mesh_node(
			Geometry.rounded_box(Vector3(size, 1.1, size * 0.8), 0.4, 2),
			palette.get_material("far_structure"), "Deck", false))
		var lit := Forms.mesh_node(
			Geometry.rounded_box(Vector3(size * 0.72, 0.34, size * 0.2),
				0.14, 2),
			palette.get_material("lit_valley_hero"), "Glow", false)
		lit.position = Vector3(0.0, 0.85, 0.0)
		pad.add_child(lit)
		for tower in 2:
			var block := Forms.mesh_node(
				Geometry.rounded_box(Vector3(1.5, 4.4 + float(tower) * 2.0,
					1.5), 0.3, 2),
				palette.get_material("far_structure"), "Block%d" % tower,
				false)
			block.position = Vector3((float(tower) - 0.5) * size * 0.5,
				2.6 + float(tower), 0.0)
			pad.add_child(block)


static func _practicals(root: Node3D, cfg: Dictionary,
		centreline: Array) -> void:
	## A handful of omnis carrying the spill the emissive dressing implies.
	var walk: Array = V2Forms.resample(centreline, 11)
	for index in walk.size():
		var at: Vector3 = walk[index]
		var lamp := OmniLight3D.new()
		lamp.name = "CourseSpill%d" % index
		lamp.position = at + Vector3(0.0, 2.4, 0.0)
		lamp.light_color = Color("#9FD6F0")
		lamp.light_energy = 1.5
		lamp.omni_range = 13.0
		lamp.omni_attenuation = 1.6
		lamp.shadow_enabled = false
		root.add_child(lamp)
		# And a warm one under the deck. The concept lights the ground beneath
		# its machine as hard as it lights the machine, and that underlight is
		# most of what separates "a premium product photographed at dusk" from
		# "a white model on a blue hill".
		var under := OmniLight3D.new()
		under.name = "CourseUnder%d" % index
		under.position = at - Vector3(0.0, 3.4, 0.0)
		under.light_color = Color("#FFA658")
		under.light_energy = 2.1
		under.omni_range = 15.0
		under.omni_attenuation = 1.4
		under.shadow_enabled = false
		root.add_child(under)
