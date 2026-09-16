extends RefCounted

## THE CONTAINED STAGE: architecture, where `environment_world.gd` builds
## landscape.
##
## V25 asked "what can a race camera see that is not the machine, the sky or a
## distant range", and answered it with rock: scarps, spires, boulders, ridges
## and a valley wall. V27 asks the same question and answers it with *built
## form* - wall panels, ribs, recessed bays, decks, overhead beams - so that a
## course can be photographed inside a room rather than on a hillside.
##
## ## This is not a second environment framework
##
## It is five more builders inside the one there is. A profile still resolves
## through `environment_profile.gd`, the sections still live under `world`, the
## build is still driven from `environment_world.BUILD_ORDER`, every form still
## lands on `WORLD_LAYER`, and every candidate is still rejected against the
## same two guides - the racing line and the camera path. Nothing here is
## reachable except from a profile that names it, and a profile shipped before
## V27 names none of these keys, so every earlier edition builds exactly what
## it built.
##
## ## Nothing here is landform and nothing here is physics
##
## Same two properties as the world file, for the same reasons, and they are
## worth restating because a *floor* is the one form in this file that sounds
## like it should be collidable:
##
##   * **No colliders.** The physics is PyBullet's, in Python. Godot only
##     photographs a replay. A deck ring is a picture of a floor.
##   * **No terrain.** `course_terrain.height` is the only ground there is; a
##     deck ring is placed *against* it and never replaces it, and no support
##     pier, camera solve or clearance number can see one.
##
## ## The vocabulary, and why it is this short
##
##     deck      the lower world: stepped plates, platforms, a pit rim
##     shell     the enclosure: a ring of wall segments with an authored rhythm
##     pylons    vertical structure between the ground and the shell
##     canopy    partial overhead: parallel ribs, a cornice ring, light frames
##     bays      local architecture at a named race node
##
## Five builders and one material family carry three very different rooms,
## which is the reusability requirement stated as a constraint on the code
## rather than as a hope about the art: a stage that needed a sixth builder per
## theme would not be a stage, it would be three sets.
##
## The one form that is deliberately *not* here is a box. There is no
## `room(width, depth, height)` anywhere in this file. A rectangular room is
## four `shell` segments and would have been the cheapest thing to write; it is
## also the thing the brief rules out, and a primitive that exists gets used.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const Terrain := preload("res://assets/marble_machine/course/course_terrain.gd")

## Every builder this file provides, in the order `environment_world` runs
## them. Deck first because everything else stands on the picture of a floor,
## shell before pylons and canopy because those two are read against it, and
## bays last because a bay is placed against a race node and has to be able to
## sit in front of whatever the shell put behind it.
const STAGE_ORDER := ["deck", "shell", "pylons", "canopy", "bays"]


static func builds(key: String) -> bool:
	return key in STAGE_ORDER


static func build(key: String, group: Node3D, palette, cfg: Dictionary,
		nodes: Dictionary, tools: Dictionary, spec: Dictionary) -> int:
	## One stage feature, by name. Returns how many nodes it made.
	##
	## `tools` carries `sited` and `why` as callables bound to the guides
	## `environment_world` already indexed - the racing line and the camera
	## path - so this file cannot honour one constraint and forget the other,
	## and cannot drift from the bucket size the index was built with.
	match key:
		"deck":
			return _deck(group, palette, cfg, tools, spec)
		"shell":
			return _shell(group, palette, cfg, tools, spec)
		"pylons":
			return _pylons(group, palette, cfg, tools, spec)
		"canopy":
			return _canopy(group, palette, cfg, tools, spec)
		"bays":
			return _bays(group, palette, cfg, nodes, tools, spec)
	return 0


# --- shared helpers ---------------------------------------------------------


static func _rand(salt: int, a: int, b: int) -> float:
	## The terrain's own lattice hash, in [0, 1). Deterministic, no RNG object.
	## The same function `environment_world` scatters with, so a stage form and
	## a rock placed from the same salt agree across machines and processes.
	return Terrain._lattice(salt, a, b)


static func _polar(centre_x: float, centre_z: float, bearing: float,
		radius: float) -> Vector2:
	## Plan position at a compass bearing. Identical convention to
	## `environment_world._polar`: bearing 0 is +Z and the swing is toward +X,
	## so a node yawed by the same angle has its local +Z pointing outward and
	## its local +X along the tangent. Every wall segment below relies on that.
	var angle := deg_to_rad(bearing)
	return Vector2(centre_x + sin(angle) * radius,
		centre_z + cos(angle) * radius)


static func _cycled(base: float, step: float, cycle: int, index: int) -> float:
	return base + step * float(index % maxi(cycle, 1))


static func _cycle_material(palette, names: Array, index: int,
		fallback: String):
	if names.is_empty():
		return palette.get_material(fallback)
	return palette.get_material(str(names[index % names.size()]))


static func _bands(spec: Dictionary) -> Array:
	## One arc, or several sharing a set of defaults.
	##
	## The same arrangement as `environment_world._bands`, and it is what makes
	## a slot canyon and a round hall the same builder: a hall is one band of
	## twenty-four segments through 360 degrees, and a canyon is two bands of
	## seven facing each other across it. Written as overrides on the parent so
	## the shared numbers - the materials, the height, the panel rhythm - are
	## authored once.
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


static func _sited(tools: Dictionary, x: float, z: float, clearance: float,
		lens: float) -> bool:
	var test: Callable = tools.get("sited", Callable())
	if not test.is_valid():
		return true
	return bool(test.call(x, z, clearance, lens))


static func _why(tools: Dictionary, x: float, z: float, clearance: float,
		lens: float) -> String:
	var reason: Callable = tools.get("why", Callable())
	if not reason.is_valid():
		return "no guides"
	return str(reason.call(x, z, clearance, lens))


static func _box(size: Vector3, fillet: float) -> ArrayMesh:
	## The one primitive almost everything here is made of.
	##
	## Filleted rather than square, and the reason is the same one
	## `lab_forms.column` gives: a square edge catches a one-pixel highlight
	## and a filleted one catches a band, and the band is what says a surface
	## was moulded rather than clipped out of a plane. At the sizes in this
	## file - wall panels tens of units across - the fillet is a fraction of a
	## unit and costs a few hundred triangles.
	var limit := minf(minf(size.x, size.y), size.z) * 0.45
	return Geometry.rounded_box(size, clampf(fillet, 0.0, maxf(limit, 0.0)), 3)


static func _slab(parent: Node3D, palette, name: String, size: Vector3,
		at: Vector3, yaw: float, material: String, fillet := 0.4,
		shadows := true) -> MeshInstance3D:
	var node := Forms.mesh_node(_box(size, fillet),
		palette.get_material(material), name, shadows)
	node.position = at
	node.rotation.y = yaw
	parent.add_child(node)
	return node


# --- A: the lower world -----------------------------------------------------


static func _deck(group: Node3D, palette, cfg: Dictionary, tools: Dictionary,
		spec: Dictionary) -> int:
	## The floor the chamber stands on, as plates rather than as a plane.
	##
	## **Why this exists at all.** Past `edge_from` the course terrain falls
	## away to `edge_y`, eighty-two units below the racing line, and from a
	## camera at y = 19 to 66 that reads as a hillside ending in a void. In a
	## landscape that void is the valley and it is correct. In a room it is a
	## hole in the floor, and one large plate laid across it at a shallow depth
	## turns the same heightfield into a landform *set into* a deck - which is
	## the whole difference between "the course was dropped in here" and "this
	## was built for it".
	##
	## Two kinds, and two is enough:
	##
	##     rings   concentric plates on the chamber axis: the floor itself,
	##             stepped so the eye can count the levels
	##     pads    rectangular platforms at a place: a landing under a race
	##             node, a service deck, a plinth
	##
	## A ring is not clearance-tested. It cannot be: it is centred on the
	## chamber axis and every one of them passes under the whole course by
	## construction, so the test that matters for a ring is the *height* one
	## below, which refuses a plate that would stand above the ground it is
	## meant to lie under.
	var node := Node3D.new()
	node.name = "StageDeck"
	group.add_child(node)
	var centre_x := float(cfg.get("centre_x", 0.0))
	var centre_z := float(cfg.get("centre_z", 0.0))
	var made := 0

	for index in (spec.get("rings", []) as Array).size():
		var ring: Dictionary = spec["rings"][index]
		# `outer` is the authored name and `radius` the compatible one: every
		# other ring-shaped spec in this system calls its size `radius`, and a
		# band has two of them.
		var outer := float(ring.get("outer", ring.get("radius", 100.0)))
		var inner := float(ring.get("inner", outer - 18.0))
		var y := float(ring.get("y", -20.0))
		var thickness := float(ring.get("thickness", 3.0))
		# **A band, never a disc, and the gorge is why.** The first build laid
		# each deck level as one filleted puck on the chamber axis, which is
		# one lathe and a few hundred triangles and looks right in plan. It is
		# wrong in section: the course crosses a ravine twenty-eight units deep
		# at `gorge_at`, and a plate spanning the axis floors it. The branches
		# cut - two routes over open air - is the depth shot of the whole film,
		# and a disc deletes it.
		#
		# So a ring is an annulus, authored inner radius first, and it is built
		# from segments rather than lathed because a faceted band carries the
		# same low-frequency rhythm as the wall above it and takes its material
		# breaks on the same facets.
		if inner >= outer:
			push_warning(("environment_stage: deck ring %d has inner %.1f "
				+ "outside outer %.1f") % [index, inner, outer])
			continue
		var highest := Terrain.height(centre_x, centre_z, cfg)
		for bearing in [0.0, 90.0, 180.0, 270.0]:
			var probe := _polar(centre_x, centre_z, bearing, inner)
			highest = maxf(highest, Terrain.height(probe.x, probe.y, cfg))
		var top := y + thickness * 0.5
		if top > highest:
			push_warning(("environment_stage: deck ring %d tops out at %.1f, "
				+ "above the ground at %.1f - it would cross the course")
				% [index, top, highest])
			continue
		var facets := maxi(int(ring.get("facets", 24)), 3)
		var mid := (outer + inner) * 0.5
		var reach := (outer - inner)
		var chord := 2.0 * mid * tan(PI / float(facets)) 			* float(ring.get("fill", 1.0))
		var materials: Array = ring.get("materials", [])
		var fallback := str(ring.get("material", "hall_deck"))
		var skip: Array = ring.get("skip", [])
		var phase := float(ring.get("bearing", 0.0))
		for step in facets:
			if step in skip:
				continue
			var bearing := phase + 360.0 / float(facets) * float(step)
			var at := _polar(centre_x, centre_z, bearing, mid)
			_slab(node, palette, "DeckRing%d_%d" % [index, step],
				Vector3(chord, thickness, reach),
				Vector3(at.x, y, at.y), deg_to_rad(bearing),
				_pick(materials, step, fallback),
				float(ring.get("fillet", 0.4)),
				bool(ring.get("shadows", false)))
			made += 1

	var clearance := float(spec.get("clearance", 7.0))
	var lens := float(spec.get("keepout", 12.0))
	for index in (spec.get("pads", []) as Array).size():
		var pad: Dictionary = spec["pads"][index]
		var at: Array = pad.get("at", [0.0, 0.0])
		var x := centre_x + float(at[0])
		var z := centre_z + float(at[1])
		# Per pad, falling back to the section's own values. A landing under
		# the finish has to set both to zero - it is deliberately *under* the
		# racing line, which is the one thing rejection sampling exists to
		# refuse - and a field that is authored but not read would make that
		# zero look like a decision when it was an accident.
		var pad_clear := float(pad.get("clearance", clearance))
		var pad_lens := float(pad.get("keepout", lens))
		if not _sited(tools, x, z, pad_clear, pad_lens):
			push_warning("environment_stage: deck pad %d is %s"
				% [index, _why(tools, x, z, pad_clear, pad_lens)])
			continue
		var size: Array = pad.get("size", [12.0, 1.4, 12.0])
		var y_value: float = float(pad["y"]) if pad.has("y") \
			else Terrain.height(x, z, cfg) - float(pad.get("sink", 0.6))
		_slab(node, palette, "DeckPad%d" % index,
			Vector3(float(size[0]), float(size[1]), float(size[2])),
			Vector3(x, y_value, z),
			deg_to_rad(float(pad.get("bearing", 0.0))),
			str(pad.get("material", "hall_deck")),
			float(pad.get("fillet", 0.5)),
			bool(pad.get("shadows", true)))
		made += 1

	made += _plates(node, palette, cfg, spec)
	return made


static func _plates(node: Node3D, palette, cfg: Dictionary,
		spec: Dictionary) -> int:
	## The third deck kind, and the one V30 exists because of: a *continuous*
	## floor, laid as a field of panels rather than as a band around a hole.
	##
	## **Why a ring could not do this.** A ring is an annulus by construction -
	## `_deck` above refuses one whose inner radius is not inside its outer -
	## and that is correct for Race #1, where the plate is a surround for a
	## heightfield and the ravine under the branches cut must stay open. Race
	## #2 stands on nothing. V29 pointed camera A at V27.2's hall and measured
	## the consequence: the centre ray passed inside the deck's 88-unit inner
	## radius on 100% of frames, the final sprint came out 90.8% black, and the
	## film overall was 64.89% nothing-drawn. The hall supplied a perimeter
	## where the picture needed a floor.
	##
	## **Why a field of panels and not one large slab.** Three reasons, and the
	## second is the one that matters:
	##
	##   1. A single plate 140 units across has one normal, one highlight and
	##      no edge inside the frame, so it reads as fog rather than as floor.
	##   2. A *seam* is free detail, and a seam every fifteen units is what
	##      gives the camera something to measure its own speed against. Camera
	##      A moves at a median 12.0 units a second and the nearest ground it
	##      ever sees is 14.3 away, which puts a panel edge across the frame
	##      about once a second - the brief's Part G, bought with geometry
	##      rather than with a texture.
	##   3. Panels can differ. `materials` cycles them, `terrace` steps them
	##      down in bands and `radius` clips the field to a disc, so the same
	##      builder makes a flat hall floor, a stepped basin and a round
	##      platform without a second code path.
	##
	## The channels between panels are not modelled. `under` lays one dark slab
	## beneath the whole field, so a gap reads as an inset channel rather than
	## as a hole onto the same black V29 was full of - one extra mesh for the
	## entire floor, which is the cheapest way to buy the brief's Part K "dark
	## inset channels" that exists.
	##
	## Not clearance-tested, for the same reason a ring is not: a floor is
	## meant to be under the racing line, and a test that refused it would be
	## refusing the feature.
	var centre_x := float(cfg.get("centre_x", 0.0))
	var centre_z := float(cfg.get("centre_z", 0.0))
	var made := 0

	for field_index in (spec.get("plates", []) as Array).size():
		var field: Dictionary = spec["plates"][field_index]
		var cells: Array = field.get("cells", [8, 8])
		var nx := maxi(int(cells[0]), 1)
		var nz := maxi(int(cells[1]), 1)
		var cell: Array = field.get("cell", [18.0, 2.4, 18.0])
		var size_x := float(cell[0])
		var size_z := float(cell[2]) if cell.size() > 2 else float(cell[0])
		var thickness := float(field.get("thickness",
			float(cell[1]) if cell.size() > 2 else 2.4))
		var gap := float(field.get("gap", 1.0))
		var at: Array = field.get("at", [0.0, 0.0])
		var origin_x := centre_x + float(at[0])
		var origin_z := centre_z + float(at[1])
		var y := float(field.get("y", -3.0))
		var pitch_x := size_x + gap
		var pitch_z := size_z + gap
		var span_x := pitch_x * float(nx)
		var span_z := pitch_z * float(nz)
		var clip := float(field.get("radius", 0.0))
		var materials: Array = field.get("materials", [])
		var fallback := str(field.get("material", "hall_deck"))
		var fillet := float(field.get("fillet", 0.35))
		var shadows := bool(field.get("shadows", false))

		# One slab under the whole field, a little larger than it and a little
		# lower, so every gap between panels shows dark lining rather than the
		# clear colour. Built first so it is behind everything it lines.
		var under: Dictionary = field.get("under", {})
		if not under.is_empty():
			var margin := float(under.get("margin", 4.0))
			var drop := float(under.get("drop", 1.2))
			var under_thick := float(under.get("thickness", 2.0))
			_slab(node, palette, "DeckUnder%d" % field_index,
				Vector3(span_x + margin * 2.0, under_thick,
					span_z + margin * 2.0),
				Vector3(origin_x, y - drop, origin_z),
				0.0, str(under.get("material", "hall_deck_dark")),
				float(under.get("fillet", 0.6)), false)
			made += 1

		# A band-wise step down away from the middle. `from` is the plan radius
		# the first step happens at and `band` how wide each tread is, so a
		# floor terraces outward without any of it being authored cell by cell.
		var terrace: Dictionary = field.get("terrace", {})
		var step_from := float(terrace.get("from", 1.0e9))
		var step_band := maxf(float(terrace.get("band", 16.0)), 0.001)
		var step_drop := float(terrace.get("step", 0.0))

		for iz in nz:
			for ix in nx:
				var x := origin_x + (float(ix) - float(nx - 1) * 0.5) * pitch_x
				var z := origin_z + (float(iz) - float(nz - 1) * 0.5) * pitch_z
				var reach := sqrt((x - origin_x) * (x - origin_x)
					+ (z - origin_z) * (z - origin_z))
				if clip > 0.0 and reach > clip:
					continue
				var level := y
				if reach > step_from and step_drop != 0.0:
					level += step_drop * floor(
						(reach - step_from) / step_band + 1.0)
				_slab(node, palette, "DeckPlate%d_%d_%d"
					% [field_index, ix, iz],
					Vector3(size_x, thickness, size_z),
					Vector3(x, level, z), 0.0,
					_pick(materials, ix + iz * nx, fallback),
					fillet, shadows)
				made += 1
	return made


# --- B: the enclosure -------------------------------------------------------


## The rhythms a shell segment can be. One base slab is built for every
## segment whatever the kind, so the enclosure is continuous by construction
## and a kind can only ever *add* to it or move it - which is what stops an
## authored rhythm from opening an accidental hole onto the sky.
const SEGMENT_KINDS := ["panel", "rib", "bay", "slot", "glass", "open"]


static func _shell(group: Node3D, palette, cfg: Dictionary,
		tools: Dictionary, spec: Dictionary) -> int:
	## The wall of the room: segments on an arc, with an authored rhythm.
	##
	## **Why segments rather than one swept surface.** A lathe would give a
	## cleaner cylinder and nothing else. What an enclosure has to do here is
	## carry low-frequency detail - the brief's Part G - and detail on a wall
	## is a *rhythm*: panel, rib, panel, bay, repeated. A segment ring makes
	## that rhythm an authored list, makes every piece of it a separate
	## silhouette against the light, and makes an opening a skipped index
	## rather than a boolean operation.
	##
	## **Why the radius is cycled rather than fixed.** A perfect circle at this
	## scale reads as a cyclorama: no corner, no facet, nothing for a raking
	## light to break on. `radius_step`/`radius_cycle` push alternate segments
	## in and out by a few units, which is the difference between a drum and a
	## lobed chamber and costs nothing.
	##
	## Every segment is tested against the camera path and nothing else. There
	## is no racing-line test because a shell stands a hundred units out and
	## could not reach the course; there *is* a lens test because a chamber
	## wall in front of a lens is not a wall, it is a lens cap, and the start
	## camera stands further out on the hillside than any other.
	var node := Node3D.new()
	node.name = "StageShell"
	group.add_child(node)
	var centre_x := float(cfg.get("centre_x", 0.0))
	var centre_z := float(cfg.get("centre_z", 0.0))
	var made := 0
	var band := 0
	for one in _bands(spec):
		made += _shell_band(node, palette, tools, one, centre_x, centre_z, band)
		band += 1
	return made


static func _shell_band(node: Node3D, palette, tools: Dictionary,
		spec: Dictionary, centre_x: float, centre_z: float,
		band: int) -> int:
	var count := int(spec.get("count", 0))
	if count <= 0:
		return 0
	var bearing_from := float(spec.get("bearing_from", 0.0))
	var bearing_step := float(spec.get("bearing_step", 360.0 / float(count)))
	var height := float(spec.get("height", 90.0))
	var foot := float(spec.get("foot", -40.0))
	var thickness := float(spec.get("thickness", 5.0))
	var fill := float(spec.get("fill", 0.98))
	var batter := float(spec.get("batter", 0.0))
	var fillet := float(spec.get("fillet", 0.5))
	var lens := float(spec.get("keepout", 34.0))
	var skip: Array = spec.get("skip", [])
	var pattern: Array = spec.get("pattern", ["panel"])
	var materials: Array = spec.get("materials", [])
	var fallback := str(spec.get("material", "hall_panel"))
	var seed_from := int(spec.get("seed_from", 4201))
	var seed_step := int(spec.get("seed_step", 19))
	var jitter := float(spec.get("height_jitter", 0.0))
	var made := 0

	for index in count:
		if index in skip:
			continue
		var kind := str(pattern[index % pattern.size()]) if not pattern.is_empty() \
			else "panel"
		if kind == "open":
			continue
		if not kind in SEGMENT_KINDS:
			push_error("environment_stage: unknown shell kind '%s'" % kind)
			kind = "panel"
		var salt := seed_from + seed_step * index
		var bearing := bearing_from + bearing_step * float(index)
		var radius := _cycled(float(spec.get("radius", 120.0)),
			float(spec.get("radius_step", 0.0)),
			int(spec.get("radius_cycle", 1)), index)
		var tall := height * (1.0 - jitter * 0.5 + jitter * _rand(salt, 3, 71))
		# A bay's back wall stands further out than its neighbours, so the
		# jambs built at the nominal radius read as a recess rather than as
		# four boxes stuck to a flat face.
		var depth := float(spec.get("bay_depth", 6.0)) if kind == "bay" else 0.0
		var at := _polar(centre_x, centre_z, bearing, radius + depth)
		if not _sited(tools, at.x, at.y, 0.0, lens):
			push_warning("environment_stage: shell segment %d/%d is %s"
				% [band, index, _why(tools, at.x, at.y, 0.0, lens)])
			continue
		var width := 2.0 * radius * sin(deg_to_rad(absf(bearing_step)) * 0.5) \
			* fill
		var yaw := deg_to_rad(bearing)
		var mount := Node3D.new()
		mount.name = "Shell%d_%d" % [band, index]
		mount.position = Vector3(at.x, 0.0, at.y)
		mount.rotation.y = yaw
		node.add_child(mount)

		# The base slab. Local +Z is radially outward, +X is the tangent, so
		# the slab's thickness is its Z and its span is its X.
		var slab := Forms.mesh_node(
			_box(Vector3(width, tall, thickness), fillet),
			_cycle_material(palette, materials, index, fallback),
			"Panel", bool(spec.get("shadows", true)))
		slab.position = Vector3(0.0, foot + tall * 0.5, 0.0)
		# `batter` leans the wall out at the top by tilting about the tangent.
		# A wall that leans away from the room makes the room read taller than
		# it is, which is the cheapest scale trick an enclosure has.
		slab.rotation.x = deg_to_rad(batter)
		mount.add_child(slab)
		made += 1

		match kind:
			"rib":
				made += _shell_rib(mount, palette, spec, width, tall, foot,
					thickness, fillet)
			"bay":
				made += _shell_bay(mount, palette, spec, width, tall, foot,
					thickness, depth, fillet)
			"slot":
				made += _shell_slot(mount, palette, spec, width, tall, foot,
					thickness)
			"glass":
				made += _shell_glass(mount, palette, spec, width, tall, foot,
					thickness, fillet)
		made += _shell_trim(mount, palette, spec, width, tall, foot, thickness,
			fillet)
	return made


static func _shell_rib(mount: Node3D, palette, spec: Dictionary, width: float,
		tall: float, foot: float, thickness: float, fillet: float) -> int:
	## A vertical pilaster standing proud of the panel behind it.
	##
	## The single most useful form in an enclosure and the reason is scale: a
	## rib is a known-thin object repeated at a known pitch, so a viewer reads
	## the wall's height off the count rather than off the frame, and the
	## height of a wall with nothing on it is unreadable at any distance.
	var rib: Dictionary = spec.get("rib", {})
	var count := int(rib.get("count", 1))
	if count <= 0:
		return 0
	var rib_width := float(rib.get("width", 2.4))
	var out := float(rib.get("depth", 2.0))
	var from := float(rib.get("from", 0.0))
	var span := float(rib.get("span", 1.0))
	var made := 0
	for which in count:
		var t: float = 0.5 if count == 1 \
			else float(which) / float(count - 1)
		var x: float = lerpf(-width * 0.5 + rib_width, width * 0.5 - rib_width, t)
		var post := Forms.mesh_node(
			_box(Vector3(rib_width, tall * span, out), fillet * 0.6),
			palette.get_material(str(rib.get("material", "hall_rib"))),
			"Rib%d" % which, true)
		post.position = Vector3(x, foot + tall * from + tall * span * 0.5,
			-(thickness * 0.5 + out * 0.5))
		mount.add_child(post)
		made += 1
	return made


static func _shell_bay(mount: Node3D, palette, spec: Dictionary, width: float,
		tall: float, foot: float, thickness: float, depth: float,
		fillet: float) -> int:
	## A recessed niche: two jambs, a head and a sill, in front of a panel that
	## already stands `depth` further out than its neighbours.
	##
	## **A niche is a light pocket, not a hole.** The brief asks for lighting
	## pockets and for wall detail at low frequency, and one form answers both:
	## the jambs put two hard vertical shadows on the wall whatever the key is
	## doing, and the recessed back face is the one surface in the room a
	## practical can wash without touching the machine.
	var bay: Dictionary = spec.get("bay", {})
	var jamb := float(bay.get("jamb", 3.0))
	var head := float(bay.get("head", 4.0))
	var sill := float(bay.get("sill", 2.0))
	var material := str(bay.get("material", "hall_panel"))
	var opening := float(bay.get("opening", 0.62))
	var lift := float(bay.get("lift", 0.16))
	var made := 0
	var face := -depth
	var inner_h := tall * opening
	var base_y := foot + tall * lift
	for side in [-1.0, 1.0]:
		_slab(mount, palette, "Jamb%d" % int(side + 2.0),
			Vector3(jamb, tall, thickness),
			Vector3(side * (width * 0.5 - jamb * 0.5),
				foot + tall * 0.5, face),
			0.0, material, fillet)
		made += 1
	var clear_width := width - jamb * 2.0
	if head > 0.0:
		_slab(mount, palette, "Head", Vector3(clear_width, head, thickness),
			Vector3(0.0, base_y + inner_h + head * 0.5, face), 0.0,
			material, fillet)
		made += 1
	if sill > 0.0:
		_slab(mount, palette, "Sill", Vector3(clear_width, sill, thickness),
			Vector3(0.0, base_y - sill * 0.5, face), 0.0, material, fillet)
		made += 1
	var strip: Dictionary = bay.get("strip", {})
	if not strip.is_empty():
		_slab(mount, palette, "BayStrip",
			Vector3(clear_width * float(strip.get("width", 0.8)),
				float(strip.get("height", 1.2)),
				float(strip.get("depth", 0.6))),
			Vector3(0.0, base_y + inner_h * float(strip.get("at", 0.94)),
				face - thickness * 0.4),
			0.0, str(strip.get("material", "lit_hall_warm")), 0.2, false)
		made += 1
	return made


static func _shell_slot(mount: Node3D, palette, spec: Dictionary, width: float,
		tall: float, foot: float, thickness: float) -> int:
	## A horizontal light strip let into the panel.
	##
	## Kept to one per segment and to a fraction of the segment's width. The
	## brief's bad list has "dozens of glowing lines" on it, and the failure
	## mode is not brightness - it is that a lit line is the highest-contrast
	## edge in any frame it appears in, so a wall of them out-reads the
	## machine at any energy above nothing.
	var slot: Dictionary = spec.get("slot", {})
	var at := float(slot.get("at", 0.58))
	_slab(mount, palette, "Slot",
		Vector3(width * float(slot.get("width", 0.72)),
			float(slot.get("height", 1.6)),
			float(slot.get("depth", 0.8))),
		Vector3(0.0, foot + tall * at, -(thickness * 0.5)),
		0.0, str(slot.get("material", "lit_hall_cool")), 0.25, false)
	return 1


static func _shell_glass(mount: Node3D, palette, spec: Dictionary,
		width: float, tall: float, foot: float, thickness: float,
		fillet: float) -> int:
	## A dark translucent insert, inset from the panel's own face.
	##
	## Glass is what keeps a graphite wall from reading as one material at
	## three values. It is also the one surface here that must never be bright:
	## a lit window is a second key, and the room already has its own.
	var glass: Dictionary = spec.get("glass", {})
	var margin := float(glass.get("margin", 3.0))
	_slab(mount, palette, "Glass",
		Vector3(maxf(width - margin * 2.0, 1.0),
			maxf(tall * float(glass.get("span", 0.56)), 1.0),
			thickness * 0.55),
		Vector3(0.0, foot + tall * float(glass.get("at", 0.5)),
			-(thickness * 0.2)),
		0.0, str(glass.get("material", "hall_glass")), fillet * 0.5, false)
	return 1


static func _shell_trim(mount: Node3D, palette, spec: Dictionary, width: float,
		tall: float, foot: float, thickness: float, fillet: float) -> int:
	## The cornice and the plinth: one band each, following the facets.
	##
	## Built per segment rather than as a hoop so that a band inherits the
	## shell's own plan - a lobed wall gets a lobed cornice - and so a skipped
	## segment takes its trim with it.
	var made := 0
	for key in ["cornice", "plinth"]:
		var trim: Dictionary = spec.get(key, {})
		if trim.is_empty():
			continue
		var band_h := float(trim.get("height", 3.0))
		var out := float(trim.get("depth", 1.6))
		var at := float(trim.get("at", 1.0 if key == "cornice" else 0.0))
		_slab(mount, palette, key.capitalize(),
			Vector3(width * float(trim.get("width", 1.0)), band_h,
				thickness + out * 2.0),
			Vector3(0.0, foot + tall * at
				+ band_h * (-0.5 if key == "cornice" else 0.5), 0.0),
			0.0, str(trim.get("material", "hall_trim")), fillet)
		made += 1
	return made


# --- C: the structure between ground and wall -------------------------------


static func _pylons(group: Node3D, palette, cfg: Dictionary,
		tools: Dictionary, spec: Dictionary) -> int:
	## Vertical structure standing on the ground between the course and the
	## shell: columns, masts, truss legs.
	##
	## **This is the parallax band, and it is the one the brief is right to
	## worry about.** A closed room's walls are far away and move slowly; the
	## machine is near and moves fast; with nothing between them a chase camera
	## produces two speeds and reads as a cutout on a backdrop. A column at
	## forty to eighty units is the third speed, and it is the only element
	## here whose *job* is motion rather than composition.
	##
	## Which is also why it is the riskiest: a column at forty units is fifteen
	## from a lens that swings past it. Every one is lens-tested, and the
	## default keep-out is the largest in this file.
	var node := Node3D.new()
	node.name = "StagePylons"
	group.add_child(node)
	var centre_x := float(cfg.get("centre_x", 0.0))
	var centre_z := float(cfg.get("centre_z", 0.0))
	var made := 0
	var band := 0
	for one in _bands(spec):
		made += _pylon_band(node, palette, cfg, tools, one, centre_x, centre_z,
			band)
		band += 1
	return made


static func _pylon_band(node: Node3D, palette, cfg: Dictionary,
		tools: Dictionary, spec: Dictionary, centre_x: float, centre_z: float,
		band: int) -> int:
	var count := int(spec.get("count", 0))
	if count <= 0:
		return 0
	var clearance := float(spec.get("clearance", 16.0))
	var lens := float(spec.get("keepout", 30.0))
	var skip: Array = spec.get("skip", [])
	var width := float(spec.get("width", 3.2))
	var depth := float(spec.get("depth", 3.2))
	var height := float(spec.get("height", 46.0))
	var sink := float(spec.get("sink", 2.0))
	var materials: Array = spec.get("materials", [])
	var fallback := str(spec.get("material", "hall_rib"))
	var made := 0
	var placed: Array = []
	for index in count:
		if index in skip:
			continue
		var salt := int(spec.get("seed_from", 5101)) \
			+ int(spec.get("seed_step", 23)) * index
		var bearing := float(spec.get("bearing_from", 0.0)) \
			+ float(spec.get("bearing_step", 360.0 / float(count))) \
			* float(index) \
			+ float(spec.get("bearing_jitter", 0.0)) * (_rand(salt, 3, 97) - 0.5)
		var radius := _cycled(float(spec.get("radius", 62.0)),
			float(spec.get("radius_step", 0.0)),
			int(spec.get("radius_cycle", 1)), index)
		var at := _polar(centre_x, centre_z, bearing, radius)
		if not _sited(tools, at.x, at.y, clearance, lens):
			continue
		var tall := height * _cycled(1.0, float(spec.get("height_step", 0.0)),
			int(spec.get("height_cycle", 1)), index)
		var ground := Terrain.height(at.x, at.y, cfg)
		var mount := Node3D.new()
		mount.name = "Pylon%d_%d" % [band, index]
		mount.position = Vector3(at.x, ground - sink, at.y)
		mount.rotation.y = deg_to_rad(bearing)
		node.add_child(mount)
		_slab(mount, palette, "Shaft", Vector3(width, tall, depth),
			Vector3(0.0, tall * 0.5, 0.0), 0.0,
			str(_pick(materials, index, fallback)),
			float(spec.get("fillet", 0.35)))
		made += 1
		var cap: Dictionary = spec.get("cap", {})
		if not cap.is_empty():
			_slab(mount, palette, "Cap",
				Vector3(width * float(cap.get("spread", 1.9)),
					float(cap.get("height", 1.6)),
					depth * float(cap.get("spread", 1.9))),
				Vector3(0.0, tall, 0.0), 0.0,
				str(cap.get("material", "hall_trim")), 0.3)
			made += 1
		var lamp: Dictionary = spec.get("lamp", {})
		if not lamp.is_empty():
			_slab(mount, palette, "PylonLight",
				Vector3(width * float(lamp.get("width", 0.7)),
					float(lamp.get("height", 1.4)),
					float(lamp.get("depth", 0.5))),
				Vector3(0.0, tall * float(lamp.get("at", 0.86)),
					-(depth * 0.5)), 0.0,
				str(lamp.get("material", "lit_hall_warm")), 0.2, false)
			made += 1
		placed.append({"at": at, "y": ground - sink, "tall": tall})

	# Cross-braces, between adjacent pylons that actually got built. Built
	# from the placed list rather than from the index so a brace can never
	# span a gap a rejection left behind - which is the one way a structural
	# form can announce that a placement failed.
	var brace: Dictionary = spec.get("brace", {})
	if not brace.is_empty() and placed.size() > 1:
		var stock := float(brace.get("stock", 0.7))
		var at_height := float(brace.get("at", 0.74))
		var gap := float(brace.get("max_span", 46.0))
		var material = palette.get_material(str(brace.get("material",
			"hall_beam")))
		for index in placed.size() - 1:
			var a: Dictionary = placed[index]
			var b: Dictionary = placed[index + 1]
			var from: Vector2 = a["at"]
			var to: Vector2 = b["at"]
			if from.distance_to(to) > gap:
				continue
			var p0 := Vector3(from.x, float(a["y"]) + float(a["tall"])
				* at_height, from.y)
			var p1 := Vector3(to.x, float(b["y"]) + float(b["tall"])
				* at_height, to.y)
			var link := Forms.mesh_node(
				Geometry.tube([p0, p1], stock, 6), material,
				"Brace%d_%d" % [band, index], false)
			node.add_child(link)
			made += 1
	return made


static func _pick(names: Array, index: int, fallback: String) -> String:
	if names.is_empty():
		return fallback
	return str(names[index % names.size()])


# --- D: partial overhead ----------------------------------------------------


static func _canopy(group: Node3D, palette, cfg: Dictionary,
		tools: Dictionary, spec: Dictionary) -> int:
	## What is above the machine, and deliberately not a ceiling.
	##
	## **The frame is 1080x1920.** A closed roof over a nine-by-sixteen picture
	## costs the top third of every wide shot and gives back a dark band; the
	## brief's Part H says so and the first build of this confirmed it. So the
	## form is parallel ribs with a hole in the middle: `skip` removes the
	## central members, the gap is where the machine is, and what remains is a
	## row of hard silhouettes across the top of the frame that say the space
	## is closed without closing it.
	##
	## Ribs are chords at a fixed y rather than an arch. An arch would be
	## prettier and would also be a curve the eye has to resolve against the
	## machine's own curves; a straight member reads as structure at any scale
	## and costs one box.
	##
	## ## The keep-out, and why it is conservative
	##
	## **A member is tested in plan at its centre and both ends, and the test
	## ignores how high it is.** That is deliberately too strict - a beam forty
	## units above a lens is harmless and this rejects it - and it is the only
	## test available: the profile's keep-out is a decimated list of *plan*
	## positions, with no heights in it, so there is nothing here to compare a
	## member's y against.
	##
	## It is also the test this builder was missing, and the render said so.
	## The first authored group crossed the merge at y = 14, four units in plan
	## from where the final camera parks at y = 24.5, and the winner frame came
	## back with a black bar diagonally across it and the FINISH board behind
	## the bar. Every other builder in this file and in `environment_world` had
	## a lens test; this one did not, because a thing that is *over* the course
	## does not sound like a thing that can be *in front of* a camera.
	var node := Node3D.new()
	node.name = "StageCanopy"
	group.add_child(node)
	var centre_x := float(cfg.get("centre_x", 0.0))
	var centre_z := float(cfg.get("centre_z", 0.0))
	var made := 0

	var ribs: Dictionary = spec.get("ribs", {})
	var count := int(ribs.get("count", 0))
	if count > 0:
		var y := float(ribs.get("y", 86.0))
		var axis := deg_to_rad(float(ribs.get("bearing", 0.0)))
		var pitch := float(ribs.get("pitch", 22.0))
		var length := float(ribs.get("length", 210.0))
		var width := float(ribs.get("width", 3.4))
		var thick := float(ribs.get("depth", 2.6))
		var skip: Array = ribs.get("skip", [])
		var materials: Array = ribs.get("materials", [])
		var fallback := str(ribs.get("material", "hall_beam"))
		var drop := float(ribs.get("drop", 0.0))
		# **A rib group is centred where it is authored, not on the chamber
		# axis, and the measurement is why.** These cameras never look above
		# their own eye height - the top of a 34-degree frame at a 30-degree
		# elevation is still 4.7 degrees below horizontal at its shallowest -
		# so a ceiling
		# over the machine is invisible at every radius. What *is* visible is
		# overhead structure above the low half of the course, where the track
		# has descended forty units and the camera has not. So the group takes
		# an offset and the profile puts it over the merge and the finish.
		# See `docs/sloped_race_v27_contained.md` and the visible-ceiling table
		# `tools/sloped_v27_contained.py --stage envelope` prints.
		var shift: Array = ribs.get("centre", [0.0, 0.0])
		var group_x := centre_x + float(shift[0])
		var group_z := centre_z + float(shift[1])
		var lens := float(ribs.get("keepout", 18.0))
		for index in count:
			if index in skip:
				continue
			var offset := (float(index) - float(count - 1) * 0.5) * pitch
			var at := Vector2(group_x + sin(axis + PI * 0.5) * offset,
				group_z + cos(axis + PI * 0.5) * offset)
			var blocked := false
			for along in [-0.5, 0.0, 0.5]:
				var probe := Vector2(at.x + sin(axis) * length * along,
					at.y + cos(axis) * length * along)
				if not _sited(tools, probe.x, probe.y, 0.0, lens):
					push_warning(("environment_stage: canopy rib %d at %.0f%% "
						+ "along is %s") % [index, along * 100.0,
						_why(tools, probe.x, probe.y, 0.0, lens)])
					blocked = true
					break
			if blocked:
				continue
			var mount := Node3D.new()
			mount.name = "CanopyRib%d" % index
			mount.position = Vector3(at.x, y - drop * absf(offset) / maxf(pitch,
				0.001), at.y)
			mount.rotation.y = axis
			node.add_child(mount)
			_slab(mount, palette, "Member", Vector3(width, thick, length),
				Vector3.ZERO, 0.0, _pick(materials, index, fallback), 0.4,
				bool(ribs.get("shadows", false)))
			made += 1
			var lamp: Dictionary = ribs.get("lamp", {})
			if not lamp.is_empty() and not index in (lamp.get("skip", []) as Array):
				_slab(mount, palette, "RibLight",
					Vector3(width * float(lamp.get("width", 0.55)),
						float(lamp.get("height", 0.6)),
						length * float(lamp.get("span", 0.62))),
					Vector3(0.0, -thick * 0.5, 0.0), 0.0,
					str(lamp.get("material", "lit_hall_cool")), 0.15, false)
				made += 1
			var hanger: Dictionary = ribs.get("hanger", {})
			if not hanger.is_empty():
				var reach := float(hanger.get("reach", 8.0))
				for side in [-1.0, 1.0]:
					_slab(mount, palette, "Hanger%d" % int(side + 2.0),
						Vector3(width * 0.5, reach, width * 0.5),
						Vector3(0.0, -reach * 0.5,
							side * length * float(hanger.get("at", 0.34))),
						0.0, str(hanger.get("material", "hall_rib")), 0.2)
					made += 1

	# A ring at the springing line: where the wall stops being a wall.
	var ring: Dictionary = spec.get("ring", {})
	if not ring.is_empty():
		var shift: Array = ring.get("centre", [0.0, 0.0])
		centre_x += float(shift[0])
		centre_z += float(shift[1])
		var band := Forms.mesh_node(
			Forms.hoop(float(ring.get("radius", 118.0)),
				float(ring.get("stock", 2.2)),
				int(ring.get("segments", 40)), 6),
			palette.get_material(str(ring.get("material", "hall_trim"))),
			"CanopyRing", false)
		band.position = Vector3(centre_x, float(ring.get("y", 74.0)), centre_z)
		node.add_child(band)
		made += 1
	return made


# --- E: architecture at a race node -----------------------------------------


static func _bays(group: Node3D, palette, cfg: Dictionary, nodes: Dictionary,
		tools: Dictionary, spec: Dictionary) -> int:
	## The local architecture that makes a race section a *place*.
	##
	## Sited from the layout's own node table - start, mix, obstacle, split,
	## merge, finish - for the reason `environment_world._landmarks` gives: a
	## place named for a race node should be at that node by construction, and
	## a site the layout has no node for is skipped, which is what lets one
	## profile run on a second course.
	##
	## A bay is **rejected and complained about** rather than nudged, for the
	## same reason a landmark is: it is authored, so a bay on the racing line
	## is a mistake in the profile and the profile is what has to change.
	##
	## Four kinds:
	##
	##     backing   a slab standing behind a node: the start's own wall
	##     alcove    a recess: back, two jambs, a head - the obstacle's pocket
	##     portal    jambs and a head with no back: a gateway to look through
	##     frame     a rectangle of members: the finish bay's proscenium
	var sites: Dictionary = spec.get("sites", {})
	if sites.is_empty():
		return 0
	var node := Node3D.new()
	node.name = "StageBays"
	group.add_child(node)
	var clearance := float(spec.get("clearance", 11.0))
	var lens := float(spec.get("keepout", 20.0))
	var made := 0
	for name in sites:
		var site: Dictionary = sites[name]
		var node_name := str(site.get("node", name))
		if not nodes.has(node_name):
			continue
		var anchor: Vector3 = nodes[node_name]
		var offset: Array = site.get("offset", [0.0, 0.0])
		var x: float = anchor.x + float(offset[0])
		var z: float = anchor.z + float(offset[1])
		var own_clear := float(site.get("clearance", clearance))
		var own_lens := float(site.get("keepout", lens))
		if not _sited(tools, x, z, own_clear, own_lens):
			push_warning("environment_stage: bay '%s' is %s"
				% [name, _why(tools, x, z, own_clear, own_lens)])
			continue
		var mount := Node3D.new()
		mount.name = "Bay%s" % str(name).capitalize()
		mount.position = Vector3(x,
			Terrain.height(x, z, cfg) + float(site.get("lift", 0.0)), z)
		mount.rotation.y = deg_to_rad(float(site.get("bearing", 0.0)))
		node.add_child(mount)
		made += _bay_form(mount, palette, site)
	return made


static func _bay_form(mount: Node3D, palette, site: Dictionary) -> int:
	var kind := str(site.get("kind", "backing"))
	var width := float(site.get("width", 26.0))
	var height := float(site.get("height", 18.0))
	var thick := float(site.get("thickness", 2.6))
	var material := str(site.get("material", "hall_panel"))
	var trim := str(site.get("trim", "hall_trim"))
	var fillet := float(site.get("fillet", 0.5))
	var jamb := float(site.get("jamb", 3.2))
	var head := float(site.get("head", 3.0))
	var sink := float(site.get("sink", 3.0))
	var made := 0

	if kind == "backing" or kind == "alcove":
		var back := float(site.get("depth", 0.0)) if kind == "alcove" else 0.0
		_slab(mount, palette, "Back", Vector3(width, height, thick),
			Vector3(0.0, height * 0.5 - sink, back), 0.0, material, fillet)
		made += 1
	if kind == "alcove" or kind == "portal" or kind == "frame":
		for side in [-1.0, 1.0]:
			_slab(mount, palette, "Jamb%d" % int(side + 2.0),
				Vector3(jamb, height, thick),
				Vector3(side * (width * 0.5 - jamb * 0.5),
					height * 0.5 - sink, 0.0),
				0.0, material, fillet)
			made += 1
		if head > 0.0:
			_slab(mount, palette, "Head",
				Vector3(width, head, thick),
				Vector3(0.0, height - sink + head * 0.5, 0.0), 0.0,
				trim, fillet)
			made += 1
	if kind == "frame":
		var sill := float(site.get("sill", 2.0))
		if sill > 0.0:
			_slab(mount, palette, "Sill", Vector3(width, sill, thick),
				Vector3(0.0, -sink - sill * 0.5, 0.0), 0.0, trim, fillet)
			made += 1

	var wing: Dictionary = site.get("wing", {})
	if not wing.is_empty():
		# Two panels splayed off the main form. What makes a fork read as a
		# choice rather than as a gap: two surfaces diverging at the angle the
		# routes diverge at, so the architecture states the split before the
		# marbles reach it.
		var span := float(wing.get("width", 18.0))
		var spread := float(wing.get("spread", 34.0))
		var reach := float(wing.get("reach", 0.5))
		for side in [-1.0, 1.0]:
			var panel := Forms.mesh_node(
				_box(Vector3(span, height * float(wing.get("span", 0.8)),
					thick), fillet),
				palette.get_material(str(wing.get("material", material))),
				"Wing%d" % int(side + 2.0), true)
			var yaw := deg_to_rad(side * spread)
			panel.position = Vector3(
				side * (width * 0.5 + cos(yaw) * span * 0.5 * reach),
				height * 0.5 * float(wing.get("span", 0.8)) - sink,
				-sin(absf(yaw)) * span * 0.5 * reach)
			panel.rotation.y = -yaw
			mount.add_child(panel)
			made += 1

	var strip: Dictionary = site.get("strip", {})
	if not strip.is_empty():
		_slab(mount, palette, "BayStrip",
			Vector3(width * float(strip.get("width", 0.72)),
				float(strip.get("height", 1.3)),
				float(strip.get("depth", 0.6))),
			Vector3(0.0, height * float(strip.get("at", 0.86)) - sink,
				-thick * 0.6),
			0.0, str(strip.get("material", "lit_hall_warm")), 0.2, false)
		made += 1
	return made
