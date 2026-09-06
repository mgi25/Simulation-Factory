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
		var edge: float = float(step[0]) + _noise(x, float(step[0]), 0.021, 5) * 7.0
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
	h += _noise(x, z, 0.098, 23) * amplitude * 0.42
	h += _noise(x, z, 0.240, 41) * amplitude * 0.16

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
	var cut: Dictionary = cfg.get("cut_index", {})
	if not cut.is_empty():
		var reach: float = float(cfg["cut_reach"])
		var inner: float = float(cfg["cut_inner"])
		var depth: float = float(cfg["cut_depth"])
		var gx := int(floor(x / reach))
		var gz := int(floor(z / reach))
		for ox in [-1, 0, 1]:
			for oz in [-1, 0, 1]:
				var bucket = cut.get(Vector2i(gx + ox, gz + oz), null)
				if bucket == null:
					continue
				for point in bucket:
					var p: Vector3 = point
					var d := Vector2(x - p.x, z - p.z).length()
					if d >= reach:
						continue
					var blend := 1.0 - smoothstep(inner, reach, d)
					h = minf(h, lerpf(h, p.y - depth, blend))

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
	var e := 3.2
	var dx := height(x + e, z, cfg, false) - height(x - e, z, cfg, false)
	var dz := height(x, z + e, cfg, false) - height(x, z - e, cfg, false)
	# 0.62 is a gradient of about 1.26, or fifty degrees. At 0.80 the wall on
	# -X and the gorge lip on +X both qualified and the whole massif came back
	# as cliff; a cliff band that covers everything separates nothing.
	if Vector3(-dx, 2.0 * e, -dz).normalized().y < 0.62:
		return "Cliff"
	# Height bands above that. Elevation is the strongest cue a mountain has
	# and the cheapest to paint: a warm valley floor, rock through the middle,
	# a pale cool cap on the crests. Slope alone put large tan blobs part way
	# up a face, which reads as camouflage rather than as ground.
	var h := height(x, z, cfg, false)
	if h < float(cfg.get("valley_below", 2.0)):
		return "Shelf"
	if h > float(cfg.get("cap_above", 34.0)):
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


static func scatter(root: Node3D, palette, cfg: Dictionary, count: int,
		avoid: Array, clearance: float) -> void:
	## Boulders on the flank, kept clear of the racing line.
	##
	## Deterministic siting, rejected wherever the sample falls within
	## `clearance` of the centreline: a rock that intersects the track is worse
	## than no rock at all, and at this density rejection is cheaper than
	## authoring every position by hand.
	var group := Node3D.new()
	group.name = "Scatter"
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
		var scale: float = 0.7 + 2.6 * _lattice(attempt, 17, 131)
		var shade := "slope_scree" if placed % 3 == 0 else "slope_rock"
		# The same smooth mass the distant ranges use, at a fiftieth of the
		# size. A rounded box on a hillside reads as a crate: it has four
		# vertical faces and a flat top, and no rock does.
		var boulder := Forms.mesh_node(
			HeroWorld.smooth_mass(scale * 1.5, scale, attempt * 7 + 3, 9, 5,
				0.42),
			palette.get_material(shade), "Rock%d" % placed, false)
		boulder.position = Vector3(x, height(x, z, cfg) - scale * 0.55, z)
		boulder.rotation.y = _lattice(attempt, 23, 7) * TAU
		boulder.rotation.z = (_lattice(attempt, 29, 11) - 0.5) * 0.45
		boulder.scale = Vector3(1.0, 0.62 + 0.5 * _lattice(attempt, 31, 13), 1.0)
		group.add_child(boulder)
	_to_world_layer(group)
