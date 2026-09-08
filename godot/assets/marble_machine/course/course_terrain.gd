extends RefCounted

## THE MOUNTAINSIDE the race is installed into.
##
## The tower build put its cliffs *behind* the machine, as a backdrop ring at
## two hundred units. A sloped course cannot do that: the brief's requirement is
## that the race runs through and along the terrain, which means the ground has
## to be a queryable surface under every metre of track, not a silhouette.
##
## So this is a heightfield rather than a set of masses. `height()` is a pure
## function of `(x, z)` and the same function builds the mesh and answers where
## a support column has to stop. Nothing anywhere else in the course guesses a
## ground height.
##
## ## The shape, and what each term is for
##
##     base grade      the whole flank falls toward +Z, the direction of travel
##     terrace steps   smoothstep drops, so the flank is a staircase of shelves
##     left rise       a rock wall on -X for the course to run along
##     right gorge     the ground falls away on +X, so a span can cross air
##     pads            flattened shelves where a module stands
##     three octaves   macro form and roughness, deterministic, no RNG
##
## The staircase matters more than it sounds. The course descends at a gentler
## average grade than the ground does, so wherever a terrace step falls under
## it the track is left standing in open air on supports, and wherever a shelf
## rises to meet it the track is cut into the hill. That alternation is what
## makes the same channel read as "hugging the mountain" in one shot and
## "flying across a gap" in the next, and it costs no extra geometry.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const HeroWorld := preload("res://assets/marble_machine/hero/hero_world.gd")

# Visual layer 2, matching `course_world.WORLD_LAYER`. The ground is part of
# the world, not part of the product, and it has to be lit by the raking key
# rather than by the three-quarter front key that models the pearl shell. On
# layer 1 the warm product key at full energy turned every lit face of the
# mountain into tan camouflage - the single worst artefact of the first study,
# and not a material problem at all.
const WORLD_LAYER := 2


static func _to_world_layer(node: Node) -> void:
	if node is VisualInstance3D:
		(node as VisualInstance3D).layers = WORLD_LAYER
	for child in node.get_children():
		_to_world_layer(child)


static func _lattice(ix: int, iz: int, salt: int) -> float:
	var n: int = (ix * 73856093) ^ (iz * 19349663) ^ (salt * 83492791)
	n = (n ^ (n >> 13)) * 1274126177
	return float((n ^ (n >> 16)) & 0xFFFF) / 65536.0


static func _noise(x: float, z: float, frequency: float, salt: int) -> float:
	## Value noise in [-1, 1]: smooth-stepped bilinear over an integer lattice.
	var fx := x * frequency
	var fz := z * frequency
	var ix := int(floor(fx))
	var iz := int(floor(fz))
	var tx := fx - float(ix)
	var tz := fz - float(iz)
	tx = tx * tx * (3.0 - 2.0 * tx)
	tz = tz * tz * (3.0 - 2.0 * tz)
	var a := _lattice(ix, iz, salt)
	var b := _lattice(ix + 1, iz, salt)
	var c := _lattice(ix, iz + 1, salt)
	var d := _lattice(ix + 1, iz + 1, salt)
	return lerpf(lerpf(a, b, tx), lerpf(c, d, tx), tz) * 2.0 - 1.0


static func height(x: float, z: float, cfg: Dictionary,
		detail := true) -> float:
	## Ground level under `(x, z)`. The only source of truth for the terrain.
	##
	## `detail = false` returns the same surface with the noise octaves left
	## off. That is what the material bands are read from: thresholding a
	## four-octave surface at a fixed height gives a fifteen-unit fringe of
	## interleaved patches wherever the surface crosses the threshold, which
	## is what made the first two studies look like camouflage. The macro
	## surface crosses each threshold once, so the bands come out as single
	## clean contours.
	# Downhill of `z_top` the flank falls at `grade`; uphill of it, at the
	# gentler `back_grade`. Without the second value the mountain above the
	# start line keeps climbing at the racing gradient and fills the top third
	# of every frame with rock; with it, the start sits under a shoulder.
	var run: float = z - float(cfg["z_top"])
	var h: float = float(cfg["top_y"]) - run * float(cfg["grade"])
	if run < 0.0:
		# Uphill of the start the flank rises to a crest and stops. A constant
		# back grade keeps climbing for the whole depth of the terrain and fills
		# every frame to its top edge with rock, which is how the first study
		# ended up with no sky in it at all. An exponential approach gives a
		# shoulder above the start line and a horizon over it.
		var rise: float = float(cfg.get("crest_rise", 15.0))
		var scale: float = float(cfg.get("crest_scale", 30.0))
		h = float(cfg["top_y"]) + rise * (1.0 - exp(run / scale))

	# The terrace edges wander with x. A step that is a straight line across
	# the whole flank reads as a machined shelf; the same step with a couple of
	# units of drift in it reads as a bench cut by the mountain.
	for entry in cfg.get("steps", []):
		var step: Array = entry
		# Two units of drift, not seven. At seven the terrace lips came out as
		# a row of sawteeth on the skyline rather than as a bench line.
		var edge: float = float(step[0]) + _noise(x, float(step[0]), 0.014, 5) * 2.4
		h -= float(step[1]) * smoothstep(
			edge - float(step[2]), edge + float(step[2]), z)

	var left: float = clampf(
		(-x - float(cfg["left_at"])) / float(cfg["left_span"]), 0.0, 1.0)
	h += float(cfg["left_rise"]) * pow(left, 1.5)

	var right: float = clampf(
		(x - float(cfg["gorge_at"])) / float(cfg["gorge_span"]), 0.0, 1.0)
	h -= float(cfg["gorge_depth"]) * pow(right, 1.4)

	var amplitude: float = float(cfg.get("noise", 1.8)) if detail else 0.0
	# Four octaves. The first is three times the amplitude of the rest and an
	# order of magnitude longer: without a macro octave a heightfield is an
	# evenly rough plane, which is what "low-poly ground" looks like however
	# fine the detail on it is. Landform first, then roughness.
	h += _noise(x, z, 0.0085, 3) * amplitude * 3.4
	h += _noise(x, z, 0.031, 7) * amplitude
	h += _noise(x, z, 0.098, 23) * amplitude * 0.55
	h += _noise(x, z, 0.240, 41) * amplitude * 0.24
	h += _noise(x, z, 0.520, 59) * amplitude * 0.10

	# Beyond the massif the ground falls away to nothing. Without this the
	# heightfield is a rectangle a hundred and seventy units across whose far
	# edge is always the highest thing in the frame, and the sky, the haze and
	# the three distant ranges are all behind it. With it the course sits on a
	# mountain that ends, and everything the world file builds is visible past
	# its shoulders.
	var reach_from: float = float(cfg.get("edge_from", 66.0))
	var reach_to: float = float(cfg.get("edge_to", 104.0))
	var radial := Vector2(x - float(cfg.get("centre_x", 0.0)),
		z - float(cfg.get("centre_z", 0.0))).length()
	var fade := smoothstep(reach_from, reach_to, radial)
	if fade > 0.0:
		h = lerpf(h, float(cfg.get("edge_y", -74.0)), fade)

	# Flattened shelves, *before* the bench and not after it. A pad pulls the
	# surface toward its own height over a radius so that a module stands on
	# ground rather than on a slope - and applied last it also pulls the ground
	# back up over the track leaving the start chute buried four units deep,
	# which is exactly what the first build of this layout did.
	for entry in cfg.get("pads", []):
		var pad: Array = entry
		var distance := Vector2(x - float(pad[0]), z - float(pad[1])).length()
		var blend := 1.0 - smoothstep(float(pad[2]),
			float(pad[2]) + float(pad[3]), distance)
		h = lerpf(h, float(pad[4]), blend)
	# The bench. Where the hill would stand higher than the racing line, it is
	# cut away to `cut_depth` below it. A real installation benches its route
	# into the slope rather than tunnelling through it, and doing it here means
	# every support has a positive length by construction rather than by
	# hand-tuned coordinates - and the cut faces it leaves behind are the most
	# rock-like thing in the frame.
	#
	# Cut from the *nearest* centreline sample, not from the union of a disc
	# per sample. Those two are not the same surface: a union of smoothstep
	# discs scallops wherever two of them meet at a shallow angle, and along
	# the ridge between two adjacent switchback benches that scalloping came
	# out as a band of sawteeth across the mountainside - the last low-poly
	# artefact in the hero frame, and one that survived a shadow-quality pass
	# and a material-band pass because it was neither.
	var cut: Dictionary = cfg.get("cut_index", {})
	if not cut.is_empty():
		var reach: float = float(cfg["cut_reach"])
		var inner: float = float(cfg["cut_inner"])
		var depth: float = float(cfg["cut_depth"])
		var gx := int(floor(x / reach))
		var gz := int(floor(z / reach))
		var nearest := reach
		var nearest_y := 0.0
		for ox in [-1, 0, 1]:
			for oz in [-1, 0, 1]:
				var bucket = cut.get(Vector2i(gx + ox, gz + oz), null)
				if bucket == null:
					continue
				for point in bucket:
					var p: Vector3 = point
					var d := Vector2(x - p.x, z - p.z).length()
					if d < nearest:
						nearest = d
						nearest_y = p.y
		if nearest < reach:
			var blend := 1.0 - smoothstep(inner, reach, nearest)
			h = minf(h, lerpf(h, nearest_y - depth, blend))

	return h


static func index_cut(cfg: Dictionary, centreline: Array) -> void:
	## Bucket the racing line so `height()` can cut the bench in constant time.
	##
	## Called once, before the mesh or any support asks for a height. Without
	## the buckets every one of sixteen thousand grid corners would test every
	## one of eight hundred centreline samples.
	var reach: float = float(cfg.get("cut_reach", 9.0))
	var buckets: Dictionary = {}
	for point in centreline:
		var p: Vector3 = point
		var key := Vector2i(int(floor(p.x / reach)), int(floor(p.z / reach)))
		if not buckets.has(key):
			buckets[key] = []
		(buckets[key] as Array).append(p)
	cfg["cut_index"] = buckets
	cfg["cut_reach"] = reach
	cfg["cut_inner"] = float(cfg.get("cut_inner", 3.4))
	cfg["cut_depth"] = float(cfg.get("cut_depth", 3.0))


static func normal(x: float, z: float, cfg: Dictionary) -> Vector3:
	return _slope(x, z, cfg, 0.35)


static func _slope(x: float, z: float, cfg: Dictionary, e: float) -> Vector3:
	var dx := height(x + e, z, cfg) - height(x - e, z, cfg)
	var dz := height(x, z + e, cfg) - height(x, z - e, cfg)
	return Vector3(-dx, 2.0 * e, -dz).normalized()


static func _material_of(x: float, z: float, cfg: Dictionary) -> String:
	## Which of the three rock surfaces belongs at `(x, z)`.
	##
	## Read off a *macro* gradient - a three-unit epsilon rather than the
	## shading normal - because a per-quad test against a four-octave surface
	## classifies the roughness rather than the landform, and the result is
	## confetti. At this epsilon the boundaries are smooth curves that follow
	## the shape of the hill, which is what a change of rock actually does.
	for entry in cfg.get("pads", []):
		var pad: Array = entry
		var reach: float = float(pad[2]) + float(pad[3]) * 0.55
		if Vector2(x - float(pad[0]), z - float(pad[1])).length() < reach:
			return "Shelf"
	# Two rock values and one very steep one, and that is deliberately all.
	#
	# The four-band version - cliff by slope, then valley / rock / cap by
	# height - was the largest remaining artefact in the hero frame. A band
	# boundary on a heightfield is assigned per quad, so it is a staircase at
	# cell resolution, and with a value jump either side of it that staircase
	# is the most visible edge on the mountain: the frame read as low-poly
	# terrain even though the surface under it is smooth-shaded. Nearly-equal
	# values make the same boundary invisible, and the *form* is carried by
	# the two-key lighting, the boulders and the scrub instead - which is how
	# the concept's environment carries it too.
	var e := 3.6
	var dx := height(x + e, z, cfg, false) - height(x - e, z, cfg, false)
	var dz := height(x, z + e, cfg, false) - height(x, z - e, cfg, false)
	if Vector3(-dx, 2.0 * e, -dz).normalized().y < 0.45:
		return "Cliff"
	if _noise(x, z, 0.017, 67) > 0.20:
		return "High"
	return "Flank"


static func build(palette, cfg: Dictionary) -> Node3D:
	## The near ground, as one smooth-shaded grid split by slope.
	##
	## Three materials keyed off the surface normal: shelf, flank and cliff
	## face. A single rock colour over a heightfield reads as a dune no matter
	## how it is lit, because the eye takes a value change as the cue for a
	## break in the rock - so the break is painted where the gradient says
	## there is one.
	var root := Node3D.new()
	root.name = "Terrain"

	var x0: float = float(cfg["x_min"])
	var x1: float = float(cfg["x_max"])
	var z0: float = float(cfg["z_min"])
	var z1: float = float(cfg["z_max"])
	var cell: float = float(cfg.get("cell", 1.7))
	var nx := int(ceil((x1 - x0) / cell))
	var nz := int(ceil((z1 - z0) / cell))

	var surfaces := {
		"Shelf": SurfaceTool.new(),
		"Flank": SurfaceTool.new(),
		"Cliff": SurfaceTool.new(),
		"High": SurfaceTool.new(),
	}
	for key in surfaces:
		(surfaces[key] as SurfaceTool).begin(Mesh.PRIMITIVE_TRIANGLES)

	for iz in nz:
		for ix in nx:
			var ax: float = x0 + float(ix) * cell
			var bx: float = ax + cell
			var az: float = z0 + float(iz) * cell
			var bz: float = az + cell
			var p00 := Vector3(ax, height(ax, az, cfg), az)
			var p10 := Vector3(bx, height(bx, az, cfg), az)
			var p11 := Vector3(bx, height(bx, bz, cfg), bz)
			var p01 := Vector3(ax, height(ax, bz, cfg), bz)
			var mid := (p00 + p10 + p11 + p01) * 0.25
			var key := _material_of(mid.x, mid.z, cfg)
			Geometry.quad_smooth_auto(surfaces[key], [p00, p01, p11, p10], [
				normal(ax, az, cfg), normal(ax, bz, cfg),
				normal(bx, bz, cfg), normal(bx, az, cfg),
			])

	var keys := {
		"Shelf": str(cfg.get("shelf_material", "slope_earth")),
		"Flank": str(cfg.get("flank_material", "slope_rock")),
		"Cliff": str(cfg.get("cliff_material", "slope_cliff")),
		"High": str(cfg.get("high_material", "slope_cap")),
	}
	for key in surfaces:
		var mesh := ArrayMesh.new()
		(surfaces[key] as SurfaceTool).commit(mesh)
		if mesh.get_surface_count() == 0:
			continue
		root.add_child(Forms.mesh_node(mesh,
			palette.get_material(str(keys[key])), str(key), false))
	_to_world_layer(root)
	return root



static func crags(root: Node3D, palette, cfg: Dictionary, count: int,
		avoid: Array, clearance: float) -> void:
	## Bedded rock outcrops on the steep ground: the cliff silhouette.
	##
	## The mountainside was reading as clay, and the reason is worth being
	## precise about because the obvious fix is the wrong one. The obvious fix
	## is to separate the ground materials again - and the sloped-course pass
	## already measured that and rejected it: a band boundary on a heightfield
	## is assigned per quad, so a value jump either side of it is a staircase
	## at cell resolution and the most visible edge on the mountain. Nothing
	## here touches `height`, `normal` or `_material_of`.
	##
	## What was actually missing is an arris. A smooth heightfield under a
	## raking key has a bright side and a dark side and no line between them,
	## and "rock" is read from lines: a bedding plane, a fracture, a ledge with
	## a shadow under it. So each outcrop is a short stack of slabs, tilted to
	## the dip of the surface under it and stepped back as it rises, and every
	## slab contributes one horizontal arris for the warm rake to catch and one
	## overhang for it to cast into.
	##
	## Sited only where the macro surface is steep. On a shelf an outcrop is a
	## boulder, and `scatter` already puts boulders on shelves; on a 40-degree
	## face it is a crag, and that face is exactly where the frame had nothing.
	var group := Node3D.new()
	group.name = "Crags"
	root.add_child(group)
	var x0: float = float(cfg["x_min"]) + 6.0
	var x1: float = float(cfg["x_max"]) - 6.0
	var z0: float = float(cfg["z_min"]) + 6.0
	var z1: float = float(cfg["z_max"]) - 6.0
	# Biased toward the lit face and the body value. An even cycle over
	# three shades puts a third of the slabs at the darkest value, and the
	# darkest value is the one that reads as a hole.
	var shades := ["crag_face", "crag_rock", "crag_face", "crag_rock",
		"crag_shadow"]

	var placed := 0
	for attempt in count * 14:
		if placed >= count:
			break
		var x: float = lerpf(x0, x1, _lattice(attempt, 37, 809))
		var z: float = lerpf(z0, z1, _lattice(attempt, 41, 907))
		# The macro gradient, at the same epsilon `_material_of` uses. Read
		# off the detail surface a crag sites itself on noise roughness
		# rather than on landform, and comes out sprinkled evenly over the
		# whole flank - which is the confetti failure in three dimensions.
		var e := 3.6
		var dx := height(x + e, z, cfg, false) - height(x - e, z, cfg, false)
		var dz := height(x, z + e, cfg, false) - height(x, z - e, cfg, false)
		var macro := Vector3(-dx, 2.0 * e, -dz).normalized()
		if macro.y > 0.86 or macro.y < 0.24:
			continue
		var too_close := false
		for point in avoid:
			var offset := Vector2(x - (point as Vector3).x,
				z - (point as Vector3).z)
			if offset.length() < clearance:
				too_close = true
				break
		if too_close:
			continue
		placed += 1
		var y: float = height(x, z, cfg)
		var outcrop := Node3D.new()
		outcrop.name = "Crag%d" % placed
		outcrop.position = Vector3(x, y, z)
		# Yawed to the dip, so the stack steps back INTO the hill rather than
		# out of it. A slab stack leaning downhill is a landslide.
		outcrop.rotation.y = atan2(macro.x, macro.z)
		group.add_child(outcrop)

		# Fewer and larger. At 2.6 the outcrops were the size of the
		# boulders already on the hill and read as more of them; a crag has
		# to be a landform, which at this camera distance starts at about
		# four units and is still subordinate to the track at ten.
		# Fewer and larger. At 2.6 the outcrops were the size of the
		# boulders already on the hill and read as more of them; a crag has
		# to be a landform, which at this camera distance starts at about
		# four units and is still subordinate to the track at ten.
		var scale: float = 4.2 + 6.4 * _lattice(attempt, 43, 1009)
		var lobes: int = 2 + int(_lattice(attempt, 47, 1103) * 3.0)
		# A cluster of overlapping masses, not a stack of slabs.
		#
		# The slab version is written out because it was tried and it failed
		# in the way this file already had a note about: `rounded_box` on a
		# hillside reads as a crate, because it has four vertical faces and a
		# flat top and no rock does. Tinting it did not help and neither did
		# tilting it - the first pass came back as grey packing cases stacked
		# on the mountain.
		#
		# `smooth_mass` is the answer the boulder scatter already found, and
		# the only thing a crag needs beyond it is a BROKEN OUTLINE: one mass
		# is a dome whatever its taper, and a dome on a slope is a bump. Two
		# or three overlapping masses at different sizes, offset across the
		# dip and buried to different depths, give the silhouette the
		# concavities that read as fracture - and a concavity is the one
		# feature a heightfield cannot produce, because a heightfield is a
		# function.
		for lobe in lobes:
			var l := float(lobe)
			var size: float = scale * (1.0 - 0.34 * l / float(lobes))
			var salt: int = attempt * 11 + lobe * 3 + 17
			# Taper low, tiers high. At the 0.46 the boulders use a mass is
			# a rounded cobble; at 0.30 it keeps its width most of the way up
			# and breaks at the top, which is what an outcrop does.
			var mass := Forms.mesh_node(
				HeroWorld.smooth_mass(size * 1.55, size * 0.72, salt,
					17, 11, 0.30),
				palette.get_material(str(shades[
					(placed + lobe) % shades.size()])),
				"Lobe%d" % lobe, false)
			var swing := TAU * _lattice(attempt + lobe, 59, 1301)
			var reach: float = scale * 0.30 * l
			mass.position = Vector3(cos(swing) * reach,
				# Buried between a third and two thirds of its own height.
				# Every lobe at one depth gives the cluster a common base
				# line, and a common base line is a plinth.
				-size * (0.30 + 0.34 * _lattice(attempt + lobe, 61, 1409)),
				sin(swing) * reach)
			mass.rotation.y = _lattice(attempt + lobe, 67, 1511) * TAU
			# Leaned a few degrees into the dip. A mass standing plumb on a
			# forty-degree face reads as placed; the strata it belongs to are
			# parallel to the hill.
			mass.rotation.z = (_lattice(attempt + lobe, 71, 1601) - 0.5) * 0.30
			mass.scale = Vector3(1.0 + 0.34 * _lattice(attempt + lobe, 73,
				1709), 1.0, 0.72 + 0.30 * _lattice(attempt + lobe, 79, 1801))
			outcrop.add_child(mass)
	_to_world_layer(group)


static func crest_ridge(root: Node3D, palette, cfg: Dictionary,
		count: int) -> void:
	## A rock skyline on the crest above the start.
	##
	## `height` gives the flank a shoulder uphill of `z_top` and then stops,
	## which is correct - it is what put a horizon over the start line instead
	## of filling the top third of the frame with rock. But the shoulder it
	## leaves is a smooth exponential dome, and a smooth dome against a dusk
	## sky is the one silhouette in the frame the eye can measure precisely.
	## So the crest gets teeth: masses standing on the shoulder line, tall
	## enough to break the horizon and thin enough not to close it.
	var group := Node3D.new()
	group.name = "CrestRidge"
	root.add_child(group)
	var z_top: float = float(cfg["z_top"])
	var centre_x: float = float(cfg.get("centre_x", 0.0))
	for index in count:
		var t := float(index) / float(maxi(count - 1, 1))
		var x: float = centre_x + lerpf(-62.0, 58.0, t) \
			+ (_lattice(index, 79, 1709) - 0.5) * 7.0
		# Uphill of the start, on the band where the shoulder flattens out.
		var z: float = z_top - 16.0 - 22.0 * _lattice(index, 83, 1801)
		var y: float = height(x, z, cfg)
		var tall: float = 7.0 + 13.0 * _lattice(index, 89, 1901)
		var mass := Forms.mesh_node(
			HeroWorld.smooth_mass(tall, tall * (0.42 + 0.20
				* _lattice(index, 97, 2003)), index * 13 + 5, 15, 9, 0.40),
			palette.get_material("crag_rock" if index % 3 else "crag_face"),
			"Tooth%d" % index, false)
		mass.position = Vector3(x, y - tall * 0.30, z)
		mass.rotation.y = _lattice(index, 101, 2111) * TAU
		group.add_child(mass)
	_to_world_layer(group)

static func scatter(root: Node3D, palette, cfg: Dictionary, count: int,
		avoid: Array, clearance: float, gauge := 1.0) -> void:
	## Boulders on the flank, kept clear of the racing line.
	##
	## Deterministic siting, rejected wherever the sample falls within
	## `clearance` of the centreline: a rock that intersects the track is worse
	## than no rock at all, and at this density rejection is cheaper than
	## authoring every position by hand.
	var group := Node3D.new()
	group.name = "Scatter%d" % int(gauge * 100.0)
	root.add_child(group)
	var x0: float = float(cfg["x_min"]) + 4.0
	var x1: float = float(cfg["x_max"]) - 4.0
	var z0: float = float(cfg["z_min"]) + 4.0
	var z1: float = float(cfg["z_max"]) - 4.0

	var placed := 0
	for attempt in count * 8:
		if placed >= count:
			break
		var x: float = lerpf(x0, x1, _lattice(attempt, 3, 61))
		var z: float = lerpf(z0, z1, _lattice(attempt, 9, 97))
		var too_close := false
		for point in avoid:
			var offset := Vector2(x - (point as Vector3).x,
				z - (point as Vector3).z)
			if offset.length() < clearance:
				too_close = true
				break
		if too_close:
			continue
		if normal(x, z, cfg).y < 0.66:
			continue
		placed += 1
		var scale: float = (0.9 + 3.4 * _lattice(attempt, 17, 131)) * gauge
		# Two values, both darker than the ground they sit on. A boulder
		# lighter than the hillside reads as a sheet of paper lying on it,
		# which is what the lighter scree value gave at this size.
		var shade := "slope_boulder" if placed % 3 == 0 else "slope_cliff"
		var salt: int = attempt * 7 + 3 + int(gauge * 1000.0)
		# The same smooth mass the distant ranges use, at a fiftieth of the
		# size. A rounded box on a hillside reads as a crate: it has four
		# vertical faces and a flat top, and no rock does.
		# Thirteen facets over seven tiers. At nine and five a mass this small
		# came out as a handful of flat plates, and a flat dark plate lying on
		# a hillside reads as a hole in it rather than as a rock on it.
		var boulder := Forms.mesh_node(
			HeroWorld.smooth_mass(scale * 1.35, scale, salt, 13, 7,
				0.46),
			palette.get_material(shade), "Rock%d" % placed, false)
		boulder.position = Vector3(x, height(x, z, cfg) - scale * 0.55, z)
		boulder.rotation.y = _lattice(attempt, 23, 7) * TAU
		boulder.rotation.z = (_lattice(attempt, 29, 11) - 0.5) * 0.45
		boulder.scale = Vector3(1.0, 0.90 + 0.30 * _lattice(attempt, 31, 13), 1.0)
		group.add_child(boulder)
	_to_world_layer(group)
