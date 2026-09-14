extends RefCounted

## THE NEAR WORLD: everything a race camera can actually see that is not the
## machine, the sky or a distant range.
##
## `environment_builder.backdrop()` builds what is beyond the near ground -
## four mass rings, a dusk band, curtains, crest lines - and V23 measured what
## that buys on this course: almost nothing. Its finding, recorded in
## `docs/sloped_race_v23.md` §13, is that **these cameras barely see the
## backdrop**, because the near terrain occludes everything below the skyline
## and the far range is a wall that hides everything behind it. Four of the six
## features V23 added move zero pixels in the twelve race moments.
##
## The cameras stand 24 to 68 units from the terrain centre at heights of 19 to
## 66. Everything they see is therefore *inside* that radius or immediately
## past it - so that is where this file builds. The rule of thumb the whole
## file follows:
##
##     under 40 units     foreground: reads as silhouette, carries the parallax
##     40 to 100 units    the ground itself, and where the machine meets it
##     100 to 240 units   midground: the gorge's far side and the inner valley
##     300 to 400 units   the valley's own outer walls: reads as scale
##     past 400 units     the backdrop's job, and it is a small one here
##
## **Those radii are read against the camera envelope, not against the
## terrain.** The first ring built here sat at 112 to 152 - thirty units past
## the terrain's own edge, which looked like the right place for a midground.
## It is not: a mass at radius 130 can be *sixty units from the lens*, and at
## sixty units a sixty-unit mass fills the frame. The marker render showed it
## occupying half of four frames out of six and covering the FINISH board in
## the payoff. A radius means nothing until it is compared with where the
## cameras stand.
##
## ## Nothing here is theme, and nothing here is landform
##
## Every form is **render-only**. There are no colliders anywhere in this scene
## - the physics is PyBullet's, in Python, and Godot only photographs a replay -
## but the stronger property is that nothing built here is ever *read* by
## anything: `sloped/terrain.py` is an exact port of `course_terrain.height`,
## every support pier stops at that surface, and a pier that landed on a rock
## this file placed would be a landform change wearing a dressing costume. So a
## form is *placed against* the terrain and never replaces it, and the whole
## section is absent from every profile shipped before V25, which is what keeps
## V22.1 and V23 reproducing byte for byte.
##
## ## The one hard constraint: the racing line
##
## Every builder rejects a candidate that falls within its own clearance of the
## centreline, tested against the raw centreline points through a bucket index
## rather than against a resampled walk. Resampling matters here: the
## centreline is seven runs concatenated, and the hop from the blue branch's
## *end* back to the orange branch's *start* is forty units of open air. A
## resampled walk puts phantom points along that hop and rejects a whole
## hillside no track goes near.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const HeroWorld := preload("res://assets/marble_machine/hero/hero_world.gd")
const Terrain := preload("res://assets/marble_machine/course/course_terrain.gd")

const WORLD_LAYER := 2

## Bucket size for the racing-line index, in layout units. Large enough that a
## clearance test of up to this value only has to look at nine buckets.
const TRACK_CELL := 10.0

## Every builder, in build order. The order is fixed here rather than taken
## from the profile's key order so that two profiles with the same sections
## build the same tree - a `Dictionary` iterates in insertion order, and a JSON
## file's insertion order is whatever its author happened to type.
const BUILD_ORDER := ["walls", "ridges", "scarps", "spires", "boulders",
	"anchors", "trees", "landmarks", "ravine", "lamps"]


# --- the entry point --------------------------------------------------------


static func build(root: Node3D, palette, cfg: Dictionary, centreline: Array,
		nodes: Dictionary, world: Dictionary) -> Dictionary:
	## Everything the profile's `world` section asks for, under one node.
	##
	## Returns a census - how many nodes each feature made - which the renderer
	## prints. A feature that silently built nothing because a count was zero
	## or a site list was empty is indistinguishable from a subtle one in a
	## still, and this pass spent its first render looking at an empty
	## `WorldForm`.
	if world.is_empty() or not bool(world.get("enabled", true)):
		return {}
	# A `world` section that carries only the camera keep-out is not a world:
	# the shared V25 profile holds the keep-out so every variant inherits one
	# list, and building an empty node for it would leave the V25 base looking
	# like a variant that failed.
	var wanted := false
	for key in BUILD_ORDER:
		if world.get(key, null) is Dictionary:
			wanted = true
			break
	if not wanted:
		return {}
	var group := Node3D.new()
	group.name = "WorldForm"
	root.add_child(group)

	# Two things a form must stay clear of, and the second one is the finding
	# this file exists to record. The racing line is obvious. The **camera
	# path** is not, and it cost a whole render pass: the start camera stands
	# on the hillside four units above the ground and twenty-two from its
	# subject, and a scarp authored on that hillside came out seven units from
	# the lens and filled the entire mixer frame - a black wall where a
	# rotor should be, in one frame out of thirteen, in all three variants at
	# once.
	#
	# The keep-out is **profile data rather than a loaded camera track** on
	# purpose. The race and the preview are two different tracks photographing
	# one scene, and a world that avoided whichever track happened to be loaded
	# would be a different world in the two renders - so the two tracks are
	# decimated into one list of points ahead of time and the profile carries
	# it. See `tools/sloped_v25_profiles.CAMERA_PATH`.
	var guides := {
		"track": _index_points(centreline),
		"lens": _index_points(world.get("keepout", [])),
	}
	var census := {}
	for key in BUILD_ORDER:
		var spec = world.get(key, null)
		if not (spec is Dictionary) or (spec as Dictionary).is_empty():
			continue
		if not bool((spec as Dictionary).get("enabled", true)):
			continue
		var made := 0
		match key:
			"walls": made = _walls(group, palette, cfg, guides, spec)
			"ridges": made = _ridges(group, palette, cfg, guides, spec)
			"scarps": made = _scarps(group, palette, cfg, guides, spec)
			"spires": made = _spires(group, palette, cfg, guides, spec)
			"boulders": made = _boulders(group, palette, cfg, guides, spec)
			"anchors": made = _anchors(group, palette, cfg, centreline, spec)
			"trees": made = _trees(group, palette, cfg, guides, spec)
			"landmarks": made = _landmarks(group, palette, cfg, guides, nodes,
				spec)
			"ravine": made = _ravine(group, palette, cfg, spec)
			"lamps": made = _lamps(group, nodes, spec)
		census[key] = made
	_to_world_layer(group)
	return census


static func _to_world_layer(node: Node) -> void:
	## The world's own light layer, so the raking `WorldKey` lights these and
	## the machine's three-quarter `Key` does not. Getting this wrong is the
	## single worst artefact this course has produced: on layer 1 the warm
	## product key turned every lit rock face into tan camouflage.
	##
	## An `OmniLight3D` is not a `VisualInstance3D` and is deliberately left
	## alone here - `_lamps` sets its own cull mask, and a light's mask and a
	## mesh's layer are different fields that happen to share a number.
	if node is VisualInstance3D:
		(node as VisualInstance3D).layers = WORLD_LAYER
	for child in node.get_children():
		_to_world_layer(child)


# --- the racing-line index --------------------------------------------------


static func _index_points(points: Array) -> Dictionary:
	## Bucket a list of plan positions for constant-time nearest queries.
	##
	## Takes `Vector3` (the centreline's own samples) or `[x, z]` pairs (a
	## profile's keep-out list, which is JSON and has no vectors in it), so one
	## index serves both and neither caller has to convert.
	var buckets := {}
	for point in points:
		var at: Vector2
		if point is Vector3:
			at = Vector2((point as Vector3).x, (point as Vector3).z)
		elif point is Array and (point as Array).size() >= 2:
			at = Vector2(float(point[0]), float(point[1]))
		else:
			continue
		var key := Vector2i(int(floor(at.x / TRACK_CELL)),
			int(floor(at.y / TRACK_CELL)))
		if not buckets.has(key):
			buckets[key] = []
		(buckets[key] as Array).append(at)
	return buckets


static func _track_gap(index: Dictionary, x: float, z: float,
		limit: float) -> float:
	## Distance from `(x, z)` to the nearest racing-line sample, in plan.
	##
	## Returns `limit` rather than the true distance once nothing is inside it,
	## because every caller only ever compares against a threshold and the
	## early exit is what makes a thousand candidate placements cheap.
	var reach := maxf(limit, 0.001)
	var span := int(ceil(reach / TRACK_CELL))
	var gx := int(floor(x / TRACK_CELL))
	var gz := int(floor(z / TRACK_CELL))
	var nearest := reach
	for ox in range(-span, span + 1):
		for oz in range(-span, span + 1):
			var bucket = index.get(Vector2i(gx + ox, gz + oz), null)
			if bucket == null:
				continue
			for point in bucket:
				var p: Vector2 = point
				var d := Vector2(x - p.x, z - p.y).length()
				if d < nearest:
					nearest = d
	return nearest


static func _clear(index: Dictionary, x: float, z: float,
		clearance: float) -> bool:
	return _track_gap(index, x, z, clearance) >= clearance


static func _sited(guides: Dictionary, x: float, z: float, clearance: float,
		lens: float) -> bool:
	## Both constraints at once: clear of the racing line, and clear of the
	## camera path. Every builder tests through this one call so that no
	## feature can be added later that honours one and forgets the other.
	if not _clear(guides["track"], x, z, clearance):
		return false
	return lens <= 0.0 or _clear(guides["lens"], x, z, lens)


# --- shared helpers ---------------------------------------------------------


static func _rand(salt: int, a: int, b: int) -> float:
	## The terrain's own lattice hash, in [0, 1). Deterministic, no RNG object,
	## and the same value for the same arguments in every process - which is
	## what makes a scatter reproducible across two machines.
	return Terrain._lattice(salt, a, b)


static func _polar(centre_x: float, centre_z: float, bearing: float,
		radius: float) -> Vector2:
	var angle := deg_to_rad(bearing)
	return Vector2(centre_x + sin(angle) * radius,
		centre_z + cos(angle) * radius)


static func _cycled(base: float, step: float, cycle: int, index: int) -> float:
	return base + step * float(index % maxi(cycle, 1))


static func _material(palette, names: Array, index: int, fallback: String):
	if names.is_empty():
		return palette.get_material(fallback)
	return palette.get_material(str(names[index % names.size()]))


static func _mass(height: float, base: float, salt: int, facets: int,
		tiers: int, taper: float) -> ArrayMesh:
	return HeroWorld.smooth_mass(height, base, salt, facets, tiers, taper)


static func _bands(spec: Dictionary) -> Array:
	## One mass ring, or several sharing a set of defaults.
	##
	## A ring is `(bearing arc, radius, height, base)`, and one ring cannot be
	## both the far side of a gorge and a mountain on the horizon: those want
	## different radii *and* different bearings, because the gorge is on one
	## side of the course and the horizon is all the way round it. `bands` is a
	## list of overrides on the parent spec, so the shared numbers - the
	## materials, the taper, the facet count - are written once and each band
	## says only what it differs by.
	var listed = spec.get("bands", null)
	if not (listed is Array) or (listed as Array).is_empty():
		return [spec]
	var out: Array = []
	for entry in listed:
		var band: Dictionary = spec.duplicate(true)
		band.erase("bands")
		for key in (entry as Dictionary):
			band[key] = (entry as Dictionary)[key]
		out.append(band)
	return out


static func _ring(node: Node3D, palette, cfg: Dictionary,
		guides: Dictionary, spec: Dictionary, label: String, band: int,
		fallback: String) -> int:
	## One mass ring: `count` smooth masses on an arc, each standing on the
	## terrain at its own bearing and radius rather than on a flat plate.
	##
	## Shared by the valley walls and the midground ridges, which differ only
	## in their radii and in which material pair they are painted from - and
	## having them differ in nothing else is what makes the recession between
	## them an argument about two numbers rather than about two builders.
	var count := int(spec.get("count", 0))
	if count <= 0:
		return 0
	var centre_x := float(cfg.get("centre_x", 0.0))
	var centre_z := float(cfg.get("centre_z", 0.0))
	var materials: Array = spec.get("materials", [])
	var facets := int(spec.get("facets", 22))
	var tiers := int(spec.get("tiers", 12))
	var taper := float(spec.get("taper", 0.30))
	var sink := float(spec.get("sink", 14.0))
	var skip: Array = spec.get("skip", [])
	var lens := float(spec.get("keepout", 48.0))
	var made := 0
	for index in count:
		if index in skip:
			continue
		var salt := int(spec.get("seed_from", 601)) \
			+ int(spec.get("seed_step", 17)) * index
		var bearing := float(spec.get("bearing_from", 90.0)) \
			+ float(spec.get("bearing_step", 27.0)) * float(index) \
			+ float(spec.get("bearing_jitter", 0.0)) \
			* (_rand(salt, 3, 811) - 0.5)
		var radius := _cycled(float(spec.get("radius", 168.0)),
			float(spec.get("radius_step", 26.0)),
			int(spec.get("radius_cycle", 3)), index)
		var height := _cycled(float(spec.get("height", 140.0)),
			float(spec.get("height_step", -18.0)),
			int(spec.get("height_cycle", 4)), index)
		var base := _cycled(float(spec.get("base", 48.0)),
			float(spec.get("base_step", 8.0)),
			int(spec.get("base_cycle", 3)), index)
		var at := _polar(centre_x, centre_z, bearing, radius)
		# A ring mass is tens of units across, so its keep-out is the
		# largest of any feature: one of these near a lens is not a
		# foreground element, it is a lens cap.
		if not _sited(guides, at.x, at.y, 0.0, lens):
			continue
		var mass := Forms.mesh_node(
			_mass(height * (0.88 + 0.24 * _rand(salt, 5, 37)),
				base * (0.88 + 0.26 * _rand(salt, 7, 41)),
				salt, facets, tiers, taper),
			_material(palette, materials, index, fallback),
			"%s%d_%d" % [label, band, index], false)
		mass.position = Vector3(at.x, Terrain.height(at.x, at.y, cfg) - sink,
			at.y)
		mass.rotation.y = float(salt) * 0.37
		node.add_child(mass)
		made += 1
		made += _crest(mass, palette, spec, salt, height, base, materials,
			fallback)
	return made


static func _crest(mass: Node3D, palette, spec: Dictionary, salt: int,
		height: float, base: float, materials: Array, fallback: String) -> int:
	## Teeth along the top of one ring mass.
	##
	## `smooth_mass` shades beautifully and silhouettes badly: three octaves of
	## noise on the radius give a face full of gullies and an outline that is
	## still a dome, and a dome at two hundred units reads as a hill of clay
	## however dark it is. This is the hero build's own fix, applied to a ring
	## rather than to a crest line - a handful of small masses sitting on the
	## shoulder, each about a sixth of the parent's height, biting notches out
	## of the edge for a few hundred triangles each.
	##
	## Sited on the parent's *shoulder* rather than its peak, because a tooth on
	## the summit reads as a hat and a tooth on the shoulder reads as a crag.
	var count := int(spec.get("crest", 0))
	if count <= 0:
		return 0
	var lift_from := float(spec.get("crest_from", 0.62))
	var lift_span := float(spec.get("crest_span", 0.26))
	var gauge := float(spec.get("crest_scale", 0.17))
	var taper := float(spec.get("taper", 0.30))
	for which in count:
		var seed_value := salt * 7 + which * 31 + 3
		var lift: float = lift_from + lift_span * _rand(seed_value, 3, 1451)
		# The parent tapers, so a tooth's stand-off has to taper with it or it
		# hangs in the air beside the shoulder it is meant to sit on.
		var out: float = base * (1.0 - taper * pow(lift, 1.45)) 			* (0.52 + 0.42 * _rand(seed_value, 5, 1453))
		var angle: float = TAU * _rand(seed_value, 7, 1459)
		var tall: float = height * gauge * (0.55 + 0.9
			* _rand(seed_value, 11, 1471))
		var tooth := Forms.mesh_node(
			_mass(tall, tall * (0.34 + 0.3 * _rand(seed_value, 13, 1481)),
				seed_value, 11, 7, 0.58),
			_material(palette, materials, which + 1, fallback),
			"Crag%d" % which, false)
		tooth.position = Vector3(cos(angle) * out, height * lift * 0.92,
			sin(angle) * out)
		tooth.rotation.y = _rand(seed_value, 17, 1487) * TAU
		tooth.rotation.z = (_rand(seed_value, 19, 1493) - 0.5) * 0.3
		mass.add_child(tooth)
	return count


# --- A: the valley walls ----------------------------------------------------


static func _walls(group: Node3D, palette, cfg: Dictionary,
		guides: Dictionary, spec: Dictionary) -> int:
	## The far side of the valley: tall masses standing on the valley floor.
	##
	## **Why these are enormous, and why that is not a mistake.** Past
	## `edge_to` the terrain has faded to `edge_y`, eighty units below the
	## racing line, and a camera at y = 30 to 66 looking downhill sees that
	## floor as the bottom of a bowl. A mass of forty units standing on it tops
	## out at minus forty and is hidden by the near ground in every frame -
	## exactly the failure V23 measured on `ridge_range`. To break the skyline
	## from these cameras a wall on the valley floor has to be a hundred units
	## or more, which is what a canyon wall *is* at this scale: the course is
	## ninety units of drop, and the valley it is cut into should be deeper
	## than the thing inside it.
	##
	## Sited by bearing so the ring can be opened where a camera needs to see
	## past it, and sunk into the floor so no mass shows a visible foot. The
	## shipped band stands at radius 300 to 392 with tops around y = +11 to
	## +54, which is the strip of sky these cameras actually see.
	var node := Node3D.new()
	node.name = "ValleyWalls"
	group.add_child(node)
	var made := 0
	var band := 0
	for one in _bands(spec):
		made += _ring(node, palette, cfg, guides, one, "Wall", band,
			"world_wall_face")
		band += 1
	return made


# --- B: the midground ridges ------------------------------------------------


static func _ridges(group: Node3D, palette, cfg: Dictionary,
		guides: Dictionary, spec: Dictionary) -> int:
	## Rock forms in the band between the terrain's edge and the valley wall.
	##
	## The layer a viewer reads "how big is this" from, and on this course it
	## was empty: the near terrain fades out by a radius of ninety-four and the
	## nearest thing V23 put beyond it stood at two hundred and six. These sit
	## at eighty to a hundred and sixty, standing on whatever the terrain
	## actually is there - which in that band is the edge fade itself, so they
	## grow out of the slope rather than out of a flat plate.
	var node := Node3D.new()
	node.name = "Ridges"
	group.add_child(node)
	var made := 0
	var band := 0
	for one in _bands(spec):
		made += _ring(node, palette, cfg, guides, one, "Ridge", band,
			"world_cliff_face")
		band += 1
	return made


# --- C: layered rock, against the near ground -------------------------------


static func _scarps(group: Node3D, palette, cfg: Dictionary,
		guides: Dictionary, spec: Dictionary) -> int:
	## Stacked ledges: the cheapest way to make a smooth heightfield read as
	## sedimentary rock.
	##
	## `course_terrain` deliberately refuses to paint band boundaries on the
	## ground, because a per-quad material boundary on a heightfield is a
	## staircase at cell resolution and reads as low-poly terrain. That
	## decision is right and it leaves the flank with no strata at all. A
	## scarp puts the strata back as *geometry* - a stack of thin slabs, each
	## narrower and set further into the hill than the one below - so a ledge
	## line is a real silhouette with a real shadow under its lip rather than a
	## painted contour.
	##
	## Sites are terrain-relative `[dx, dz, bearing, scale]`, so a profile
	## authored against one layout is not nonsense on another.
	var sites: Array = spec.get("sites", [])
	if sites.is_empty():
		return 0
	var node := Node3D.new()
	node.name = "Scarps"
	group.add_child(node)
	var centre_x := float(cfg.get("centre_x", 0.0))
	var centre_z := float(cfg.get("centre_z", 0.0))
	var materials: Array = spec.get("materials", [])
	var tiers := int(spec.get("tiers", 5))
	var size: Array = spec.get("size", [13.0, 1.5, 5.0])
	var rise := float(spec.get("rise", 1.7))
	var inset := float(spec.get("inset", 1.15))
	var shrink := float(spec.get("shrink", 0.86))
	var sink := float(spec.get("sink", 1.4))
	var clearance := float(spec.get("clearance", 6.0))
	var lens := float(spec.get("keepout", 24.0))
	var made := 0
	for which in sites.size():
		var site: Array = sites[which]
		var x := centre_x + float(site[0])
		var z := centre_z + float(site[1])
		if not _sited(guides, x, z, clearance, lens):
			push_warning(("environment_world: scarp %d is inside the racing "
				+ "line or the camera path and was dropped") % which)
			continue
		var bearing := float(site[2])
		var gauge: float = float(site[3]) if site.size() > 3 else 1.0
		var stack := Node3D.new()
		stack.name = "Scarp%d" % which
		stack.position = Vector3(x, Terrain.height(x, z, cfg) - sink, z)
		stack.rotation.y = deg_to_rad(bearing)
		node.add_child(stack)
		for tier in tiers:
			var shrunk: float = pow(shrink, float(tier))
			var salt := which * 31 + tier
			var slab := Forms.mesh_node(
				Geometry.rounded_box(Vector3(
					float(size[0]) * gauge * shrunk,
					float(size[1]) * gauge,
					float(size[2]) * gauge * shrunk),
					float(size[1]) * gauge * 0.38, 2),
				_material(palette, materials, tier, "world_cliff_ledge"),
				"Ledge%d" % tier, false)
			# Each ledge is set back into the hill and swung a few degrees off
			# the one below it. Perfectly stacked slabs read as a staircase,
			# which is a built thing; a few degrees of drift reads as bedding.
			slab.position = Vector3(
				(_rand(salt, 3, 97) - 0.5) * float(size[0]) * 0.16,
				rise * gauge * float(tier),
				-inset * gauge * float(tier))
			slab.rotation.y = (_rand(salt, 7, 101) - 0.5) * 0.18
			slab.rotation.x = (_rand(salt, 11, 103) - 0.5) * 0.07
			stack.add_child(slab)
			made += 1
	return made


# --- D: teeth on the skyline ------------------------------------------------


static func _spires(group: Node3D, palette, cfg: Dictionary,
		guides: Dictionary, spec: Dictionary) -> int:
	## Thin rock masses on the near ground, biased uphill and to the crest.
	##
	## The terrain's silhouette from every race camera is a smooth dome, and a
	## smooth dome reads as a mound of clay however well it is lit. What breaks
	## it is a fringe of tall narrow forms on the ridge that bite irregular
	## notches out of the skyline - the one idea carried over unchanged from
	## the hero build's gorge walls, where it cost almost no triangles and did
	## most of the work.
	##
	## Deliberately *not* scattered over the whole flank: a spire beside the
	## track is a distraction and a spire in the middle of a shelf is a
	## chimney. `zone` is a terrain-relative box, and its default is the uphill
	## wall.
	var count := int(spec.get("count", 0))
	if count <= 0:
		return 0
	var node := Node3D.new()
	node.name = "Spires"
	group.add_child(node)
	var centre_x := float(cfg.get("centre_x", 0.0))
	var centre_z := float(cfg.get("centre_z", 0.0))
	var zone: Array = spec.get("zone", [-70.0, -22.0, -70.0, 40.0])
	var clearance := float(spec.get("clearance", 9.0))
	var lens := float(spec.get("keepout", 17.0))
	var materials: Array = spec.get("materials", [])
	var height := float(spec.get("height", 9.0))
	var spread := float(spec.get("height_spread", 7.0))
	var base := float(spec.get("base", 2.1))
	var taper := float(spec.get("taper", 0.66))
	var facets := int(spec.get("facets", 12))
	var tiers := int(spec.get("tiers", 8))
	var sink := float(spec.get("sink", 1.1))
	var lean := float(spec.get("lean", 0.11))
	var made := 0
	for attempt in count * 9:
		if made >= count:
			break
		var x: float = centre_x + lerpf(float(zone[0]), float(zone[1]),
			_rand(attempt, 5, 1013))
		var z: float = centre_z + lerpf(float(zone[2]), float(zone[3]),
			_rand(attempt, 9, 1019))
		if not _sited(guides, x, z, clearance, lens):
			continue
		# Not on a face the ground itself has already made into a cliff: a
		# spire growing out of a vertical rock wall reads as a glitch.
		if Terrain.normal(x, z, cfg).y < float(spec.get("min_normal", 0.58)):
			continue
		made += 1
		var salt := attempt * 13 + 5
		var tall: float = height + spread * _rand(salt, 3, 1021)
		var spire := Forms.mesh_node(
			_mass(tall, base * (0.7 + 0.7 * _rand(salt, 7, 1031)), salt,
				facets, tiers, taper),
			_material(palette, materials, made, "world_scarp"),
			"Spire%d" % made, false)
		spire.position = Vector3(x, Terrain.height(x, z, cfg) - sink, z)
		spire.rotation.y = _rand(salt, 11, 1033) * TAU
		spire.rotation.z = (_rand(salt, 17, 1039) - 0.5) * lean
		node.add_child(spire)
	return made


# --- E: the foreground ------------------------------------------------------


static func _boulders(group: Node3D, palette, cfg: Dictionary,
		guides: Dictionary, spec: Dictionary) -> int:
	## Large rock forms in a band beside the racing line: the foreground.
	##
	## **This is the parallax feature.** A backdrop at three hundred units
	## moves by nothing when the camera travels twenty; a six-unit rock fifteen
	## units off the track sweeps across a third of the frame in the same move.
	## The chase cameras run the length of the course at between fifteen and
	## forty units from the pack, so a band just outside the track's own
	## clearance is the one place geometry is guaranteed both visible and
	## fast-moving.
	##
	## The band is expressed as a distance from the racing line rather than as
	## a region of the map, which is what keeps it beside the *course* on any
	## layout: `near` and `far` bracket it, and a candidate outside the bracket
	## is rejected rather than nudged - a nudged rock is one that ends up on
	## the bracket's edge, and a ring of rocks at a constant offset from the
	## track reads as a kerb.
	var count := int(spec.get("count", 0))
	if count <= 0:
		return 0
	var node := Node3D.new()
	node.name = "Boulders"
	group.add_child(node)
	var x0 := float(cfg.get("x_min", -80.0)) + 3.0
	var x1 := float(cfg.get("x_max", 80.0)) - 3.0
	var z0 := float(cfg.get("z_min", -90.0)) + 3.0
	var z1 := float(cfg.get("z_max", 108.0)) - 3.0
	var near := float(spec.get("near", 7.5))
	var far := float(spec.get("far", 22.0))
	var materials: Array = spec.get("materials", [])
	var scale := float(spec.get("scale", 3.4))
	var spread := float(spec.get("scale_spread", 3.6))
	var taper := float(spec.get("taper", 0.44))
	var facets := int(spec.get("facets", 15))
	var tiers := int(spec.get("tiers", 9))
	var sink := float(spec.get("sink", 0.55))
	# The smallest keep-out of any feature, and deliberately so: a boulder
	# sweeping past nine units from the lens *is* the parallax this pass is
	# for. What it may not do is stand between the camera and the pack.
	var lens := float(spec.get("keepout", 9.0))
	var made := 0
	for attempt in count * 14:
		if made >= count:
			break
		var x: float = lerpf(x0, x1, _rand(attempt, 7, 1049))
		var z: float = lerpf(z0, z1, _rand(attempt, 13, 1051))
		var gap := _track_gap(guides["track"], x, z, far + 0.5)
		if gap < near or gap > far:
			continue
		if not _sited(guides, x, z, 0.0, lens):
			continue
		if Terrain.normal(x, z, cfg).y < float(spec.get("min_normal", 0.6)):
			continue
		made += 1
		var salt := attempt * 19 + 7
		var size: float = scale + spread * _rand(salt, 3, 1061)
		var rock := Forms.mesh_node(
			_mass(size * (0.7 + 0.6 * _rand(salt, 5, 1063)), size, salt,
				facets, tiers, taper),
			_material(palette, materials, made, "world_scarp"),
			"Rock%d" % made, false)
		rock.position = Vector3(x, Terrain.height(x, z, cfg) - size * sink, z)
		rock.rotation.y = _rand(salt, 7, 1069) * TAU
		rock.rotation.z = (_rand(salt, 11, 1087) - 0.5) * 0.32
		node.add_child(rock)
	return made


# --- F: where the machine meets the ground ----------------------------------


static func _anchors(group: Node3D, palette, cfg: Dictionary,
		centreline: Array, spec: Dictionary) -> int:
	## An engineered platform on the ground under a run of supports.
	##
	## The brief's most important request and the one a still cannot fake: a
	## support column that simply intersects a hillside reads as a model stood
	## on a table, and the fix is not a longer column but *a foundation*. Each
	## anchor is a cut pad of rock with a retaining wall of blocks around its
	## downhill lip and a graphite sill where the pier lands, sited directly
	## under the racing line wherever the track is high enough above the ground
	## for the gap to be visible at all.
	##
	## **Under the line, not beside it, and never a surface.** The pad's top is
	## the ground's own height, so it adds nothing a pier could land on that
	## was not already there - `course_machine` has placed every pier against
	## `Terrain.height` before this runs, and nothing here moves that surface.
	## What an anchor adds is a *rim*: a lip and a wall that read as excavation
	## around a foot that would otherwise emerge from smooth clay.
	var every := float(spec.get("every", 26.0))
	if every <= 0.0:
		return 0
	var node := Node3D.new()
	node.name = "Anchors"
	group.add_child(node)
	var min_drop := float(spec.get("min_drop", 4.5))
	var max_drop := float(spec.get("max_drop", 26.0))
	var pad := float(spec.get("pad", 4.6))
	var lip := float(spec.get("lip", 0.9))
	var blocks := int(spec.get("blocks", 7))
	var wall := float(spec.get("wall", 1.5))
	var deck: String = str(spec.get("deck", "world_deck"))
	var kerb: String = str(spec.get("kerb", "world_deck_dark"))
	var stone: String = str(spec.get("stone", "world_scarp"))
	var travelled := 0.0
	var made := 0
	var limit := int(spec.get("limit", 14))
	for step in range(1, centreline.size()):
		if made >= limit:
			break
		var here: Vector3 = centreline[step]
		var previous: Vector3 = centreline[step - 1]
		var leg := here.distance_to(previous)
		# A hop between two runs is not a length of track. Counting it drifts
		# the spacing and, at the branch handoff, jumps forty units at once.
		if leg > 4.0:
			continue
		travelled += leg
		if travelled < every:
			continue
		var ground := Terrain.height(here.x, here.z, cfg)
		var drop := here.y - ground
		if drop < min_drop or drop > max_drop:
			continue
		travelled = 0.0
		made += 1
		var forward := (here - previous).normalized()
		var site := Node3D.new()
		site.name = "Anchor%d" % made
		site.position = Vector3(here.x, ground, here.z)
		site.rotation.y = atan2(forward.x, forward.z)
		node.add_child(site)
		# The cut platform: a shallow disc of rock sunk almost flush, so its
		# rim is a thin bright line on the hillside rather than a plinth.
		var slab := Forms.mesh_node(
			Geometry.rounded_disc(pad, lip, lip * 0.4, 18, 3),
			palette.get_material(stone), "Pad", false)
		slab.position.y = -lip * 0.28
		site.add_child(slab)
		# The retaining wall, as cut blocks around the downhill lip rather than
		# as one ring. A continuous kerb reads as a moulded base; separate
		# blocks with gaps between them read as masonry, which is the whole
		# difference between a toy's plinth and an installation's foundation.
		for which in blocks:
			var angle: float = PI * (float(which) / float(maxi(blocks - 1, 1))
				- 0.5) * float(spec.get("sweep", 1.15))
			var block := Forms.mesh_node(
				Geometry.rounded_box(Vector3(
					pad * float(spec.get("block_width", 0.36)),
					wall * (0.74 + 0.5 * _rand(made * 17 + which, 3, 1237)),
					pad * 0.24), 0.11, 2),
				palette.get_material(kerb), "Block%d" % which, false)
			block.position = Vector3(sin(angle) * pad * 0.9, wall * 0.28,
				cos(angle) * pad * 0.9)
			block.rotation.y = angle
			site.add_child(block)
		# And the sill the pier lands on: graphite, square, small, and the one
		# part of an anchor that is machine rather than ground.
		var sill := Forms.mesh_node(
			Geometry.rounded_box(Vector3(pad * 0.5, 0.42, pad * 0.5),
				0.12, 2), palette.get_material(deck), "Sill", false)
		sill.position.y = 0.22
		site.add_child(sill)
	return made


# --- G: vegetation ----------------------------------------------------------


static func _trees(group: Node3D, palette, cfg: Dictionary,
		guides: Dictionary, spec: Dictionary) -> int:
	## Stylised conifers in sparse clusters, with low shrubs between them.
	##
	## A conifer here is one tapered mass with eight facets - the same
	## generator the cliffs use, driven to a near-cone. It is a silhouette and
	## nothing else, which is the correct amount of tree for a world whose job
	## is to sit behind a white machine: at 270 pixels wide a modelled branch
	## structure is four dark pixels either way, and what a viewer reads off
	## vegetation at that size is *scale* and *edge*, not species.
	##
	## Sparse on purpose. The brief asks for pockets rather than a carpet, and
	## a carpet would also be the one dressing that could genuinely compete
	## with the racers: eight hundred small high-contrast objects across a
	## frame is visual noise however dark each one is.
	var clusters := int(spec.get("clusters", 0))
	if clusters <= 0:
		return 0
	var node := Node3D.new()
	node.name = "Trees"
	group.add_child(node)
	var x0 := float(cfg.get("x_min", -80.0)) + 4.0
	var x1 := float(cfg.get("x_max", 80.0)) - 4.0
	var z0 := float(cfg.get("z_min", -90.0)) + 4.0
	var z1 := float(cfg.get("z_max", 108.0)) - 4.0
	var clearance := float(spec.get("clearance", 6.5))
	var lens := float(spec.get("keepout", 8.0))
	var reach := float(spec.get("reach", 34.0))
	var per := int(spec.get("per_cluster", 4))
	var vary := int(spec.get("cluster_spread", 3))
	var radius := float(spec.get("spread", 3.2))
	var height := float(spec.get("height", 3.0))
	var tall := float(spec.get("height_spread", 2.6))
	var stem := float(spec.get("width", 0.62))
	var taper := float(spec.get("taper", 0.93))
	var facets := int(spec.get("facets", 8))
	var tiers := int(spec.get("tiers", 5))
	var materials: Array = spec.get("materials", [])
	var shrubs: Array = spec.get("shrubs", [])
	var shrub_every := maxi(int(spec.get("shrub_every", 3)), 1)
	var made := 0
	var placed := 0
	for attempt in clusters * 12:
		if placed >= clusters:
			break
		var x: float = lerpf(x0, x1, _rand(attempt, 11, 1091))
		var z: float = lerpf(z0, z1, _rand(attempt, 17, 1093))
		var gap := _track_gap(guides["track"], x, z, reach + 0.5)
		if gap < clearance or gap > reach:
			continue
		if not _sited(guides, x, z, 0.0, lens):
			continue
		if Terrain.normal(x, z, cfg).y < float(spec.get("min_normal", 0.72)):
			continue
		placed += 1
		var clump := Node3D.new()
		clump.name = "Copse%d" % placed
		clump.position = Vector3(x, Terrain.height(x, z, cfg), z)
		node.add_child(clump)
		var count: int = per + int(_rand(attempt, 19, 1097) * float(vary))
		for which in count:
			var salt := attempt * 29 + which * 7 + 3
			var angle: float = TAU * _rand(salt, 3, 1103)
			var out: float = radius * (0.25 + 0.9 * _rand(salt, 5, 1109))
			var tx: float = x + cos(angle) * out
			var tz: float = z + sin(angle) * out
			if not _sited(guides, tx, tz, clearance, lens):
				continue
			var top: float = height + tall * _rand(salt, 7, 1117)
			var mesh: ArrayMesh
			var key: String
			if which % shrub_every == shrub_every - 1 and not shrubs.is_empty():
				mesh = _mass(top * 0.32, stem * 2.0, salt, 7, 3, 0.42)
				key = str(shrubs[which % shrubs.size()])
			elif materials.is_empty():
				mesh = _mass(top, stem * (0.8 + 0.5 * _rand(salt, 11, 1123)),
					salt, facets, tiers, taper)
				key = "conifer_deep"
			else:
				mesh = _mass(top, stem * (0.8 + 0.5 * _rand(salt, 11, 1123)),
					salt, facets, tiers, taper)
				key = str(materials[which % materials.size()])
			var tree := Forms.mesh_node(mesh, palette.get_material(key),
				"Tree%d" % which, false)
			tree.position = Vector3(cos(angle) * out,
				Terrain.height(tx, tz, cfg) - clump.position.y - top * 0.06,
				sin(angle) * out)
			tree.rotation.y = _rand(salt, 13, 1129) * TAU
			clump.add_child(tree)
			made += 1
	return made


# --- H: the landmarks -------------------------------------------------------


static func _landmarks(group: Node3D, palette, cfg: Dictionary,
		guides: Dictionary, nodes: Dictionary, spec: Dictionary) -> int:
	## One memorable rock form at each named race location.
	##
	## Sited from the layout's own `nodes` table - start, mix, obstacle, split,
	## merge, finish - so a landmark is at the place it is named for by
	## construction rather than by a coordinate somebody has to keep in step
	## with a layout table. A site the layout has no node for is skipped, which
	## is what lets one profile run on a second course.
	##
	## Three kinds, and three is enough:
	##
	##     butte   one broad flat-topped mass: a platform the eye returns to
	##     spires  two to four tall thin masses: a cluster with a silhouette
	##     gate    a pair either side of a bearing, framing the gap between
	##
	## The gate is the one that earns its place. A route split a viewer has to
	## be told about is not a junction; two different cliff silhouettes either
	## side of the fork make the choice a *place*.
	var sites: Dictionary = spec.get("sites", {})
	if sites.is_empty():
		return 0
	var node := Node3D.new()
	node.name = "Landmarks"
	group.add_child(node)
	# **A landmark is rejected rather than nudged, and it complains.** Every
	# other builder here places by rejection sampling and a rejected candidate
	# costs nothing; a landmark is authored, so a landmark that lands on the
	# track is a mistake in the profile and the profile is what has to change.
	# Silently sliding it out of the way would hide the mistake and move a
	# named place away from the place it is named for.
	var clearance := float(spec.get("clearance", 12.0))
	var lens := float(spec.get("keepout", 26.0))
	var made := 0
	for name in sites:
		if not nodes.has(name):
			continue
		var site: Dictionary = sites[name]
		var anchor: Vector3 = nodes[name]
		var offset: Array = site.get("offset", [0.0, 0.0])
		var x: float = anchor.x + float(offset[0])
		var z: float = anchor.z + float(offset[1])
		var sink := float(site.get("sink", 3.0))
		var mount := Node3D.new()
		mount.name = "Mark%s" % str(name).capitalize()
		mount.position = Vector3(x, Terrain.height(x, z, cfg) - sink, z)
		node.add_child(mount)
		var kind := str(site.get("kind", "butte"))
		var salt := int(site.get("seed", 1201))
		var height := float(site.get("height", 18.0))
		var base := float(site.get("base", 9.0))
		var material: String = str(site.get("material", "world_cliff_face"))
		match kind:
			"butte":
				if not _sited(guides, x, z, clearance, lens):
					push_warning(("environment_world: landmark '%s' is "
						+ "inside %.1f of the racing line or %.1f of the "
						+ "camera path") % [name, clearance, lens])
					continue
				var mass := Forms.mesh_node(
					_mass(height, base, salt, int(site.get("facets", 20)),
						int(site.get("tiers", 12)),
						float(site.get("taper", 0.22))),
					palette.get_material(material), "Butte", false)
				mass.rotation.y = float(salt) * 0.31
				mount.add_child(mass)
				made += 1
			"spires":
				var count := int(site.get("count", 3))
				var lean := float(site.get("spread", 5.0))
				for which in count:
					var seed_value := salt + which * 23
					var angle: float = TAU * float(which) 						/ float(maxi(count, 1)) + float(salt) * 0.1
					var at := Vector3(cos(angle) * lean, 0.0,
						sin(angle) * lean)
					# Checked before the mesh is generated, not after. A form
					# built and then abandoned is an orphan `Node3D` holding a
					# mesh RID, and Godot reports exactly that at exit.
					if not _sited(guides, x + at.x, z + at.z, clearance, lens):
						push_warning(("environment_world: landmark '%s' spire "
							+ "%d is inside %.1f of the racing line or %.1f of "
							+ "the camera path")
							% [name, which, clearance, lens])
						continue
					var tall: float = height * (0.62 + 0.55
						* _rand(seed_value, 3, 1151))
					var spire := Forms.mesh_node(
						_mass(tall, base * (0.24 + 0.2
							* _rand(seed_value, 5, 1153)), seed_value,
							int(site.get("facets", 13)),
							int(site.get("tiers", 9)),
							float(site.get("taper", 0.6))),
						palette.get_material(material),
						"Spire%d" % which, false)
					spire.position = Vector3(at.x,
						Terrain.height(x + at.x, z + at.z, cfg)
							- mount.position.y - sink * 0.4, at.z)
					spire.rotation.y = _rand(seed_value, 7, 1163) * TAU
					spire.rotation.z = (_rand(seed_value, 11, 1171) - 0.5) * 0.13
					mount.add_child(spire)
					made += 1
			"gate":
				var bearing := deg_to_rad(float(site.get("bearing", 90.0)))
				var half := float(site.get("gap", 15.0)) * 0.5
				for side in [-1.0, 1.0]:
					var seed_value := salt + int(side * 37.0)
					var at := Vector3(sin(bearing) * half * side, 0.0,
						cos(bearing) * half * side)
					if not _sited(guides, x + at.x, z + at.z, clearance, lens):
						push_warning(("environment_world: landmark '%s' post "
							+ "%d is inside %.1f of the racing line or %.1f of "
							+ "the camera path")
							% [name, int(side), clearance, lens])
						continue
					var tall: float = height * (1.0 if side > 0.0
						else float(site.get("ratio", 0.68)))
					var pillar := Forms.mesh_node(
						_mass(tall, base, seed_value,
							int(site.get("facets", 17)),
							int(site.get("tiers", 11)),
							float(site.get("taper", 0.38))),
						palette.get_material(material),
						"Post%d" % int(side), false)
					pillar.position = Vector3(at.x,
						Terrain.height(x + at.x, z + at.z, cfg)
							- mount.position.y - sink, at.z)
					pillar.rotation.y = float(seed_value) * 0.43
					mount.add_child(pillar)
					made += 1
			_:
				push_error("environment_world: unknown landmark kind '%s'"
					% kind)
	return made


# --- I: the ravine ----------------------------------------------------------


static func _ravine(group: Node3D, palette, cfg: Dictionary,
		spec: Dictionary) -> int:
	## A dark water floor in the gorge, with rock banks either side of it.
	##
	## The course's whole east side is open air over a gorge, and open air with
	## nothing at the bottom of it is a hole rather than a drop. V23's mist
	## decks gave the gorge *air*; this gives it a *floor*, which is what turns
	## the same shot from "the track ends" into "the track is high".
	##
	## **Nearly flat, nearly black, and only slightly reflective.** The
	## environment samples its reflections from the sky and this sky is a
	## near-black dusk, so a mirror down there returns almost nothing: what
	## makes the surface read is the *contrast* between a smooth plane and the
	## broken rock around it, plus whatever the crest lights and the finish
	## practical throw across it. A high-metallic water would be a black hole
	## with a hard edge, which is worse than no water at all.
	var node := Node3D.new()
	node.name = "Ravine"
	group.add_child(node)
	var at_x := float(spec.get("at_x",
		float(cfg.get("gorge_at", 15.0)) + 34.0))
	var at_z := float(spec.get("at_z", float(cfg.get("centre_z", 0.0))))
	var level := float(spec.get("level", -62.0))
	var made := 0
	if bool(spec.get("water", true)):
		var size: Array = spec.get("size", [74.0, 132.0])
		var pool := Forms.mesh_node(
			Geometry.rounded_box(Vector3(float(size[0]), 1.2,
				float(size[1])), float(spec.get("round", 16.0)), 3),
			palette.get_material(str(spec.get("material", "world_water"))),
			"Water", false)
		pool.position = Vector3(at_x, level, at_z)
		pool.rotation.y = deg_to_rad(float(spec.get("bearing", 0.0)))
		node.add_child(pool)
		made += 1
	var banks := int(spec.get("banks", 0))
	var bank_material: String = str(spec.get("bank_material", "world_wet"))
	for which in banks:
		var salt := 1301 + which * 29
		var side: float = -1.0 if which % 2 == 0 else 1.0
		var along: float = (_rand(salt, 3, 1181) - 0.5) \
			* float(spec.get("bank_span", 110.0))
		var out: float = float(spec.get("bank_offset", 36.0)) \
			* side * (0.8 + 0.4 * _rand(salt, 5, 1187))
		var tall: float = float(spec.get("bank_height", 26.0)) \
			* (0.6 + 0.8 * _rand(salt, 7, 1193))
		var slab := Forms.mesh_node(
			_mass(tall, float(spec.get("bank_base", 15.0))
				* (0.7 + 0.6 * _rand(salt, 11, 1201)), salt, 15, 9, 0.30),
			palette.get_material(bank_material), "Bank%d" % which, false)
		slab.position = Vector3(at_x + out, level - tall * 0.22, at_z + along)
		slab.rotation.y = float(salt) * 0.27
		node.add_child(slab)
		made += 1
	return made


# --- J: the practicals ------------------------------------------------------


static func _lamps(group: Node3D, nodes: Dictionary, spec: Dictionary) -> int:
	## A handful of omnis out in the world, away from the course.
	##
	## Not on the machine and not on the track: those already have six zone
	## practicals and a full mast rig. These are the distant, low-energy lights
	## that say the valley is inhabited - and there are three or four of them,
	## because the brief's own warning is the correct one. A dark world will
	## take any amount of light before it looks full, and the frame where it
	## starts looking full is the frame where the machine has stopped being the
	## brightest thing in it.
	##
	## Sites are `[node, dx, dy, dz, colour, energy, range, attenuation?]`
	## relative to a named layout node, so a lamp is placed against the race
	## rather than against a map.
	var sites: Array = spec.get("sites", [])
	if sites.is_empty():
		return 0
	var made := 0
	for entry in sites:
		var site: Array = entry
		var name := str(site[0])
		if not nodes.has(name):
			continue
		var anchor: Vector3 = nodes[name]
		var lamp := OmniLight3D.new()
		lamp.name = "WorldLamp%d" % made
		lamp.position = anchor + Vector3(float(site[1]), float(site[2]),
			float(site[3]))
		lamp.light_color = Color(str(site[4]))
		lamp.light_energy = float(site[5])
		lamp.omni_range = float(site[6])
		lamp.omni_attenuation = float(site[7]) if site.size() > 7 else 1.5
		lamp.shadow_enabled = false
		# **World layer only.** A practical out on the hillside that also lit
		# the machine would be a second key nobody asked for, and the one rule
		# this pass may not break is that the machine's light is the machine's.
		lamp.light_cull_mask = 1 << (WORLD_LAYER - 1)
		group.add_child(lamp)
		made += 1
	return made
