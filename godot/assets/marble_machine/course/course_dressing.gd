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
const HeroWorld := preload("res://assets/marble_machine/hero/hero_world.gd")


static func build(root: Node3D, palette, cfg: Dictionary, centreline: Array,
		nodes: Dictionary) -> void:
	var group := Node3D.new()
	group.name = "Dressing"
	root.add_child(group)
	_lamps(group, palette, cfg, centreline)
	_scrub(group, palette, cfg, centreline)
	# Cover at the scale a hillside is read at, not at the scale a bush is.
	# `_scrub` places 74 clumps of half-metre boxes, which is correct at ten
	# units and gone at sixty - and sixty is where most of the mountain in
	# any section frame actually is.
	_foliage(group, palette, cfg, centreline)
	_pylons(group, palette, cfg)
	# The warmth the world's raking key gave up. It was a 2.3-energy orange
	# directional turning whole planes tan; this is the same warmth attached
	# to things that could plausibly be emitting it, which is both more
	# honest and - because it is local - far more readable.
	_outposts(group, palette, cfg, centreline)
	_valley(group, palette, cfg)
	Terrain._to_world_layer(group)
	# The lamp heads and beacons are emissive geometry on the world layer, so
	# they light nothing on their own. Six omnis carry the actual spill, sited
	# where the densest run of masts is rather than one per mast.
	_practicals(root, cfg, centreline)


static func _lamps(root: Node3D, palette, cfg: Dictionary,
		centreline: Array) -> void:
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
	# 11 units put twenty-one masts on two hundred and thirty of course, and
	# in a wide frame that is a picket fence: the eye counts poles instead of
	# following a track. At 17 there are fourteen, and every third one is
	# tall - so the row has a beat in it rather than a pitch, which is what
	# separates "service lighting was installed along here" from "a column
	# was instanced at a fixed interval".
	var spacing := 17.0
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
		# A mast stands on the ground only where the ground is right there.
		#
		# This was measured rather than guessed, and the first guess was
		# wrong in an instructive way. The masts that read as dangling wires
		# in a section frame turned out not to be the tall ones over the
		# gorge - those are twelve units of column and they read as pylons,
		# which is fine. They were the FOUR unit ones on the open slope: at
		# that length a 0.13 tube with a footing box on the end of it is a
		# plumb line, and there is no distance at which it is not, because
		# the thing that makes it read as a plumb line is the dark blob at
		# the bottom rather than the length of the line.
		#
		# So the threshold is not about absurdity, it is about clutter, and
		# it belongs almost at zero. Past a unit and a half the lamp is
		# bracketed off the track structure - which is what an installation
		# on a raised route actually does, keeps every mast the same short
		# length whatever the ground is doing underneath, and leaves the
		# hillside clear.
		var deck_mounted: bool = here.y - ground > 1.6
		var base_y: float = here.y - 1.05 if deck_mounted else ground
		var mast := Node3D.new()
		mast.name = "Mast%d" % index
		mast.position = Vector3(at.x, base_y, at.z)
		mast.rotation.y = atan2(side.x, side.z)
		group.add_child(mast)

		# Every third mast is a zone marker: half again as tall, warm lensed,
		# and carrying the beat. The two between it are short service lamps.
		var marker: bool = index % 3 == 1
		var lift: float = 2.30 if marker else 1.15
		var height: float = lift + 1.05 if deck_mounted 			else maxf(here.y - ground + lift, 2.2)
		var column := Forms.mesh_node(
			Geometry.tube([Vector3.ZERO, Vector3(0.0, height, 0.0)], 0.15, 8),
			palette.get_material("graphite"), "Column", false)
		mast.add_child(column)
		# On the ground, a footing plate; on the deck, a bracket reaching
		# back to the keel. Both are the same idea - a mast has to be seen
		# to be attached to something.
		if deck_mounted:
			# A bracket triangle back to the keel, and the sign matters: the
			# mast is yawed so local +Z points AWAY from the track - which is
			# why the arm carrying the lamp head uses a negative reach - so a
			# bracket built toward +Z reaches out into clear air and renders
			# as a bar floating beside the channel, attached to nothing. It
			# has to go the same way the arm does.
			#
			# The stand-off is 2.35 and the shell's outer shoulder is at 1.13,
			# so a reach of 1.32 lands the foot on the shoulder rather than
			# short of it or inside the running surface.
			for member in [[0.62, 0.50], [0.06, 0.46]]:
				var strut := Forms.mesh_node(
					Forms.brace(Vector3(0.0, float(member[0]), 0.0),
						Vector3(0.0, float(member[1]), -1.32), 0.085, 8),
					palette.get_material("graphite"), "Bracket%d"
						% int(float(member[0]) * 100.0), false)
				mast.add_child(strut)
			var shoe := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.34, 0.20, 0.46), 0.06, 2),
				palette.get_material("graphite_plate_polish"), "Shoe", false)
			shoe.position = Vector3(0.0, 0.46, -1.34)
			mast.add_child(shoe)
		else:
			var foot := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.62, 0.34, 0.62), 0.10, 2),
				palette.get_material("graphite_deep"), "Foot", false)
			foot.position = Vector3(0.0, 0.10, 0.0)
			mast.add_child(foot)
		# The arm leans back over the track, which is where the light is
		# wanted and also what keeps the mast's silhouette off the channel.
		# A shorter reach and a smaller head. At 1.30 out and 0.46 across the
		# head was the largest dark object at its own distance and it read as
		# a weight hanging off a wire - a lamp is supposed to be a bright
		# point with a shade over it, and the shade is not the subject.
		var reach := -0.86
		var arm := Forms.mesh_node(
			Geometry.tube([Vector3(0.0, height, 0.0),
				Vector3(0.0, height + 0.22, reach)], 0.062, 8),
			palette.get_material("graphite"), "Arm", false)
		mast.add_child(arm)
		var shade := Forms.mesh_node(
			Geometry.rounded_disc(0.21, 0.17, 0.06, 14, 3),
			palette.get_material("graphite_soft"), "Shade", false)
		shade.position = Vector3(0.0, height + 0.24, reach)
		mast.add_child(shade)
		# The lens faces down out of the shade and is the brightest thing on
		# the mast, which is the whole point of putting one there.
		var lens := Forms.mesh_node(
			Geometry.rounded_disc(0.155, 0.12, 0.04, 14, 3),
			palette.get_material("lit_ridge_warm_polish" if marker
				else "lit_cyan_soft"), "Lens", false)
		lens.position = Vector3(0.0, height + 0.15, reach)
		mast.add_child(lens)
		if not marker:
			continue
		# A collar on the zone markers, so the beat is visible in silhouette
		# as well as in colour.
		var collar := Forms.mesh_node(
			Forms.hoop(0.20, 0.045, 12, 6),
			palette.get_material("gold_dark"), "Collar", false)
		collar.position = Vector3(0.0, height * 0.62, 0.0)
		mast.add_child(collar)


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


static func _foliage(root: Node3D, palette, cfg: Dictionary,
		centreline: Array) -> void:
	## Stands of cover at the scale a hillside is read at.
	##
	## `_scrub` is right and is kept: half-metre bushes in clumps, on the
	## flatter ground, read correctly at ten units and are most of what makes
	## a terrace look walked on. What it cannot do is carry the middle
	## distance, because a half-metre object at sixty units is a pixel - and
	## sixty units is where most of the mountain in any section frame is.
	##
	## So this is the same idea one order of magnitude up: stands of three to
	## six canopies, each a smooth mass two to four units across, sited on
	## gentler ground and clear of the racing line by a wide margin. A stand
	## is darker than the rock it sits on at every distance, which is the one
	## rule the boulder scatter already established and the one that keeps
	## vegetation reading as cover rather than as debris.
	var group := Node3D.new()
	group.name = "Foliage"
	root.add_child(group)
	var x0: float = float(cfg.get("centre_x", 0.0)) - 66.0
	var x1: float = float(cfg.get("centre_x", 0.0)) + 66.0
	var z0: float = float(cfg.get("centre_z", 0.0)) - 70.0
	var z1: float = float(cfg.get("centre_z", 0.0)) + 70.0
	var placed := 0
	for attempt in 1100:
		if placed >= 44:
			break
		var x: float = lerpf(x0, x1, Terrain._lattice(attempt, 103, 2203))
		var z: float = lerpf(z0, z1, Terrain._lattice(attempt, 107, 2309))
		# Gentler than a crag wants and steeper than a shelf: the band a
		# treeline actually occupies. Anything flatter is where `_scrub` and
		# the modules are, anything steeper is bare rock.
		var up: float = Terrain.normal(x, z, cfg).y
		if up < 0.74 or up > 0.97:
			continue
		var clear := true
		for point in centreline:
			var offset := Vector2(x - (point as Vector3).x,
				z - (point as Vector3).z)
			# Twice the scrub's margin. A stand is four units across and
			# three tall, and one of those beside the channel is an
			# occlusion rather than a dressing.
			if offset.length() < 8.6:
				clear = false
				break
		if not clear:
			continue
		placed += 1
		var y: float = Terrain.height(x, z, cfg)
		var stand := Node3D.new()
		stand.name = "Stand%d" % placed
		stand.position = Vector3(x, y, z)
		group.add_child(stand)
		var count := 3 + int(Terrain._lattice(attempt, 109, 2411) * 4.0)
		for tree in count:
			var salt: int = attempt * 13 + tree * 5 + 7
			var size: float = 1.15 + 1.35 * Terrain._lattice(salt, 113, 2503)
			var canopy := Forms.mesh_node(
				HeroWorld.smooth_mass(size * 1.30, size, salt, 11, 7, 0.62),
				palette.get_material("foliage_canopy" if tree % 3
					else "foliage_deep"), "Canopy%d" % tree, false)
			var angle := TAU * Terrain._lattice(salt, 127, 2609)
			var reach: float = 0.8 + 3.1 * Terrain._lattice(salt, 131, 2707)
			canopy.position = Vector3(cos(angle) * reach, -size * 0.42,
				sin(angle) * reach)
			canopy.rotation.y = angle
			canopy.scale = Vector3(1.0, 0.78 + 0.34
				* Terrain._lattice(salt, 137, 2803), 1.0)
			stand.add_child(canopy)


static func _outposts(root: Node3D, palette, cfg: Dictionary,
		centreline: Array) -> void:
	## Small warm buildings on the flank: what says the mountain is inhabited.
	##
	## The sloped-course pass named this gap honestly and did not close it:
	## "the concept's environment is warmer and far more densely dressed -
	## foliage, lit ground, warm architecture at the base. Ours has lamp
	## masts, ridge pylons, scrub and valley platforms, and is still the
	## cooler frame." The architecture it did have was six slab towers at
	## three hundred and thirty units, which is far enough that they read as
	## crest rather than as building.
	##
	## ## Sited in the frame, not on a bearing
	##
	## The first pass placed them on bearings from the course centre, and most
	## of them landed uphill behind the crest where no camera on this course
	## can see them - which is the same mistake in siting that "signs face
	## downhill" is in orientation, and it comes from the same cause: every
	## camera here stands below and downhill of its subject, so the visible
	## ground is a wedge and not a ring.
	##
	## So they are given explicit offsets from the course centre, chosen
	## against three facts about this terrain: the massif is solid out to a
	## radius of about fifty-eight and fades to the valley floor by ninety;
	## the wall rises on -X and the gorge falls away on +X; and the course
	## itself occupies x -19..24, z -37..46. That leaves two bands that are
	## both on real ground and in shot - the wall shoulder to the left of the
	## course, and the gorge lip to its right.
	##
	## Each is a warm-walled block with a lit window band, a lean-to roof and
	## a lamp on a short mast. Deliberately small: the brief's rule for
	## supports applies to scenery too - intentional, and subordinate.
	var group := Node3D.new()
	group.name = "Outposts"
	root.add_child(group)
	var centre_x: float = float(cfg.get("centre_x", 0.0))
	var centre_z: float = float(cfg.get("centre_z", 0.0))
	# x offset, z offset, size, warm. Left of the course on the wall
	# shoulder, and right of it on the gorge lip.
	var sites := [
		[-34.0, -26.0, 3.0, true], [-40.0, -4.0, 3.8, true],
		[-33.0, 20.0, 3.2, true], [-38.0, 42.0, 4.2, true],
		[32.0, -30.0, 2.8, false], [37.0, -6.0, 3.4, true],
		[34.0, 24.0, 3.0, true], [40.0, 50.0, 4.4, true],
		[-14.0, 66.0, 4.6, true], [16.0, 70.0, 3.6, false],
	]
	for index in sites.size():
		var site: Array = sites[index]
		var size: float = float(site[2])
		var warm: bool = bool(site[3])
		var x: float = centre_x + float(site[0])
		var z: float = centre_z + float(site[1])
		var angle := atan2(float(site[0]), float(site[1]))
		# Rejected outright rather than nudged if it lands on the course.
		# A nudge is how a building ends up half inside a viaduct.
		var clear := true
		for point in centreline:
			if Vector2(x - (point as Vector3).x,
					z - (point as Vector3).z).length() < 12.0:
				clear = false
				break
		if not clear:
			continue
		var y: float = Terrain.height(x, z, cfg)
		var post := Node3D.new()
		post.name = "Outpost%d" % index
		post.position = Vector3(x, y, z)
		# Turned to face the way every camera looks from: downhill and
		# outward, so the lit window band is never on the far side.
		post.rotation.y = angle + PI
		group.add_child(post)

		var wall = palette.get_material("warm_structure" if warm
			else "far_structure")
		var deep = palette.get_material("warm_structure_deep")
		var lit = palette.get_material("lit_far_warm_polish" if warm
			else "lit_far_window_hero")

		# A terrace cut for it to stand on, so it is not a block on a slope.
		post.add_child(Forms.mesh_node(
			Geometry.rounded_box(Vector3(size * 2.4, size * 0.5,
				size * 2.0), 0.16, 2), deep, "Terrace", false))
		var body := Forms.mesh_node(
			Geometry.rounded_box(Vector3(size * 1.5, size * 0.92,
				size * 1.1), 0.14, 2), wall, "Body", false)
		body.position = Vector3(0.0, size * 0.62, 0.0)
		post.add_child(body)
		# A lean-to over it, offset so the silhouette is not a cube.
		var roof := Forms.mesh_node(
			Geometry.rounded_box(Vector3(size * 1.74, size * 0.16,
				size * 1.34), 0.08, 2), deep, "Roof", false)
		roof.position = Vector3(0.0, size * 1.12, size * 0.06)
		roof.rotation.x = deg_to_rad(-7.0)
		post.add_child(roof)
		# The window band, on the downhill face - which is the only face any
		# camera on this course ever sees, and the same reason the signs
		# face downhill.
		var window := Forms.mesh_node(
			Geometry.rounded_box(Vector3(size * 1.16, size * 0.28,
				size * 0.10), 0.04, 2), lit, "Window", false)
		window.position = Vector3(0.0, size * 0.66, size * 0.58)
		post.add_child(window)
		var lamp_mast := Forms.mesh_node(
			Geometry.tube([Vector3.ZERO, Vector3(0.0, size * 1.5, 0.0)],
				0.07, 6), palette.get_material("graphite"), "Mast", false)
		lamp_mast.position = Vector3(size * 1.05, 0.0, size * 0.72)
		post.add_child(lamp_mast)
		var head := Forms.mesh_node(
			Geometry.rounded_disc(0.24, 0.19, 0.06, 12, 3), lit, "Head",
			false)
		head.position = Vector3(size * 1.05, size * 1.5, size * 0.72)
		post.add_child(head)

		# One omni per outpost, small and warm, on the world layer's own
		# scale. The emissive bands light nothing by themselves and a warm
		# building whose ground is cool reads as a decal.
		if not warm:
			continue
		var glow := OmniLight3D.new()
		glow.name = "OutpostGlow%d" % index
		glow.position = Vector3(x, y + size * 0.8, z)
		glow.light_color = Color("#FFB06A")
		glow.light_energy = 2.4
		glow.light_cull_mask = Terrain.WORLD_LAYER
		glow.omni_range = size * 5.0
		glow.omni_attenuation = 1.5
		glow.shadow_enabled = false
		root.add_child(glow)

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
	# Eleven over three depth bands rather than seven on one arc. The gorge
	# is the whole right-hand third of a wide frame and its floor was a
	# single ring of platforms at one distance, which gives the drop a bottom
	# but not a depth. Staggering the reach gives it both.
	for index in 11:
		var angle := deg_to_rad(-46.0 + float(index) * 15.0)
		var reach: float = 40.0 + 15.0 * float(index % 3) 			+ 9.0 * float(index % 2)
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
			palette.get_material("lit_valley_warm_polish"), "Glow", false)
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
	## A handful of omnis carrying the spill the emissive dressing implies -
	## and carrying the cool-to-warm journey while they do it.
	##
	## The eleven cool and eleven warm lights were one colour each down two
	## hundred and thirty units, which spends the most powerful tool available
	## for a temperature progression on nothing at all. The edge lights and
	## the guard tints already step through seven zones; these now step with
	## them, so the *air* around the track changes temperature as the race
	## goes on rather than only the trim on it.
	##
	## Read along the walk: cyan off the line, aqua, a neutral violet through
	## the middle, and gold from the choice to the flag. `walk` is resampled
	## over the whole centreline in order, so the index IS the progress
	## fraction and no extra bookkeeping is needed.
	var stops := [
		Color("#7FE9FF"), Color("#7FE9FF"), Color("#88E4EA"),
		Color("#9DD8E6"), Color("#B4B8EE"), Color("#C0AEE8"),
		Color("#D2B9DC"), Color("#E8C7B4"), Color("#FFC98C"),
		Color("#FFC078"), Color("#FFB86A"),
	]
	var walk: Array = V2Forms.resample(centreline, 11)
	for index in walk.size():
		var at: Vector3 = walk[index]
		var t := float(index) / float(maxi(walk.size() - 1, 1))
		var tint: Color = stops[clampi(index, 0, stops.size() - 1)]
		var lamp := OmniLight3D.new()
		lamp.name = "CourseSpill%d" % index
		lamp.position = at + Vector3(0.0, 2.4, 0.0)
		lamp.light_color = tint
		# 1.5 was set against a 3.2 key and a 1.16 glow threshold, and it was
		# adding to the surface the review called a blown-out white road. The
		# spill is here to say the lamp masts are working, not to expose the
		# channel.
		lamp.light_energy = 1.05
		lamp.omni_range = 13.0
		lamp.omni_attenuation = 1.6
		lamp.shadow_enabled = false
		root.add_child(lamp)
		# And a warm one under the deck. The concept lights the ground beneath
		# its machine as hard as it lights the machine, and that underlight is
		# most of what separates "a premium product photographed at dusk" from
		# "a white model on a blue hill". It warms as the course descends,
		# which is also what a valley floor at dusk actually does.
		var under := OmniLight3D.new()
		under.name = "CourseUnder%d" % index
		under.position = at - Vector3(0.0, 3.4, 0.0)
		under.light_color = Color("#FF9A54").lerp(Color("#FFC489"),
			1.0 - t)
		under.light_energy = lerpf(1.9, 2.6, t)
		under.omni_range = 15.0
		under.omni_attenuation = 1.4
		under.shadow_enabled = false
		root.add_child(under)
