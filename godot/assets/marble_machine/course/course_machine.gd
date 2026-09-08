extends RefCounted

## Assembles a sloped course from a layout table.
##
## One builder for both phases. `detail = "block"` draws the signature channel,
## the terrain and plain marker volumes where the modules will go - enough to
## judge a *shape* and nothing more, which is what the layout study is for.
## `detail = "hero"` swaps the markers for the authored modules.
##
## The track itself is `v2/v2_track.gd` unchanged: the six-feature banked
## cross-section is the one asset from the tower build that transfers to a
## sloped course without an argument, because it was always designed as a
## length of channel rather than as part of a column.
##
## ## Supports belong to the track above them, not to a spine
##
## Every run is walked at a fixed arc-length interval and asked how far its keel
## is above `course_terrain.height` at that point. Under about a metre it gets a
## graphite plinth; above that, a Y-frame column or a pair of splayed legs; over
## a gap deeper than eight units it gets a trestle with a cross-braced frame.
## Nothing is placed by hand and nothing hangs off anything else, which is the
## structural half of "this is not a tower".

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Track := preload("res://assets/marble_machine/v2/v2_track.gd")
const Terrain := preload("res://assets/marble_machine/course/course_terrain.gd")
const Layout := preload("res://assets/marble_machine/course/course_layout.gd")
const Modules := preload("res://assets/marble_machine/course/course_modules.gd")
const FinishArena := preload("res://assets/marble_machine/course/course_finish.gd")
const Dressing := preload("res://assets/marble_machine/course/course_dressing.gd")

const KEEL_DROP := 0.98         # v2_track's keel bottom, in profile units
# Fewer piers, each carrying more. At 5.6 a viaduct over the gorge came
# out as a picket fence of thin frames; at 7.4 each one is a structure.
const SUPPORT_SPACING := 7.4
const RACERS := 8

# The colour story, read *along* the course rather than down a tower. Cyan off
# the line, cooling through the first two legs, violet on the approach to the
# choice, the two route identities at the choice itself and gold from the merge
# to the flag - so a viewer who has seen four seconds of the Short can tell
# roughly how far through the race a frame is from its edge lights alone.
const EDGE_LIGHTS := {
	"launch": "lit_cyan_line_polish",
	"leg1": "lit_aqua_line_polish",
	"leg2": "lit_violet_cool_polish",
	"leg3": "lit_violet_line_polish",
	"blue": "lit_blue_line_polish",
	"orange": "lit_orange_line_polish",
	"final": "lit_gold_line_polish",
}

# The guard tint follows the same journey. Carrying temperature in the guard
# as well as in the edge light is what makes a zone read at phone size, where
# a 0.062 tube is two pixels and a wall down both sides of the channel is
# twenty - and it does it without touching the shell, so the track is still
# visibly one product from end to end rather than seven painted sections.
const GUARDS := {
	"launch": "acrylic_guard_polish",
	"leg1": "acrylic_guard_polish",
	"leg2": "acrylic_violet_polish",
	"leg3": "acrylic_violet_polish",
	"blue": "acrylic_blue_polish",
	"orange": "acrylic_amber_polish",
	"final": "acrylic_gold_polish",
}


static func build(palette, key: String, options: Dictionary = {}) -> Node3D:
	var table := Layout.table(key)
	var terrain_cfg: Dictionary = table["terrain"]
	var detail := str(options.get("detail", "block"))

	var root := Node3D.new()
	root.name = "Course"
	root.set_meta("layout", key)

	var centreline: Array = []
	var runs := Node3D.new()
	runs.name = "Runs"
	root.add_child(runs)

	var total_length := 0.0
	var clearances: Array = []
	for entry in table["runs"]:
		var spec: Dictionary = entry
		var name := str(spec["name"])
		var role := str(spec["role"])
		var light := str(EDGE_LIGHTS.get(name, "lit_cyan_line_polish"))
		var shell := "shell_pearl_polish"
		var floor_key := "running_pearl_polish"
		var guard := str(GUARDS.get(name, "acrylic_guard_polish"))
		if name == "blue":
			shell = "blue_machine"
			floor_key = "running_blue_polish"
		elif name == "orange":
			shell = "orange_machine"
			floor_key = "running_orange_polish"
		elif role == "sprint":
			shell = "shell_pearl_warm_polish"
			floor_key = "running_warm_polish"

		var run := Track.build(palette, spec["controls"], name.capitalize(), {
			"scale": float(spec["scale"]),
			"bank_gain": float(spec["bank_gain"]),
			"bank_max": float(spec["bank_max"]),
			"edge_light": light,
			"edge_stock": 0.062,
			"shell": shell,
			"floor": floor_key,
			"guard": guard,
			"samples": int(options.get("samples", 118)),
			"ribs": detail != "block",
		})
		runs.add_child(run)
		var path: Array = run.get_meta("path")
		total_length += V2Forms.path_length(path)
		root.set_meta("%s_path" % name, path)
		root.set_meta("%s_banks" % name, run.get_meta("banks"))
		root.set_meta("%s_scale" % name, float(spec["scale"]))
		centreline.append_array(path)

	# Order matters and is the whole reason this is not one loop. The bench is
	# cut from the racing line, the ground is built from the cut, and a support
	# is only as long as the ground under it - so the track has to exist before
	# the terrain does, and the terrain before any pier.
	Terrain.index_cut(terrain_cfg, V2Forms.resample(centreline,
		maxi(centreline.size() / 3, 8)))
	var ground := Terrain.build(palette, terrain_cfg)
	root.add_child(ground)

	# Paired by index rather than by name, and that is a bug fix.
	#
	# `Track.build` is handed `name.capitalize()`, and GDScript's `capitalize`
	# inserts a space before a digit - so the run called "leg1" becomes a node
	# called "Leg 1", and looking its spec back up by `name.to_lower()` asks
	# the table for "leg 1" and misses. The old lookup pushed an error and
	# fell back to `runs[0]`, which is `launch`, three times per build.
	#
	# It has been harmless so far only by coincidence: launch, leg1, leg2 and
	# leg3 all carry `HERO_SCALE`, so the wrong spec supplied the right
	# number. The moment a leg is given a scale of its own - which is exactly
	# the kind of change a start-fairness pass makes - the supports under
	# three of the four longest runs would silently be built at the wrong
	# gauge. The children of `runs` are appended in table order, so the index
	# is the reliable key and no string has to round-trip.
	var run_nodes: Array = runs.get_children()
	for at in run_nodes.size():
		var run: Node3D = run_nodes[at]
		var spec: Dictionary = table["runs"][at]
		clearances.append_array(_supports(root, palette, run, terrain_cfg,
			float(spec["scale"]), str(spec["name"])))

	_markers(root, palette, table, detail)
	_modules(root, palette, table, detail)
	_field(root, palette, table)
	# Two scatters at two scales. The large one reads at a hundred units and
	# the small one at ten, and a section shot is framed at ten - one pass at
	# a single size leaves the near ground smooth in exactly the frames where
	# the ground is a third of the picture.
	Terrain.scatter(ground, palette, terrain_cfg,
		int(options.get("rocks", 64)), centreline, 5.4)
	Terrain.scatter(ground, palette, terrain_cfg,
		int(options.get("pebbles", 110)), centreline, 3.1, 0.34)
	# Rock structure, on top of the two boulder gauges rather than instead of
	# them. Boulders are objects lying ON the hill and read at ten and at a
	# hundred units; crags are outcrops OF it and are the only thing in the
	# frame that gives a steep face an arris. The crest teeth are separate
	# because they are sited against the horizon rather than against the
	# gradient - a silhouette is a different job from a surface.
	Terrain.crags(ground, palette, terrain_cfg,
		int(options.get("crags", 38)), centreline, 7.2)
	Terrain.crest_ridge(ground, palette, terrain_cfg,
		int(options.get("crest_teeth", 13)))
	if detail != "block":
		Dressing.build(root, palette, terrain_cfg, centreline,
			table["nodes"])

	root.set_meta("metrics", _metrics(table, total_length, clearances,
		centreline))
	# The terrain config as it ended up, bench index and all.
	#
	# `Layout.table` hands out a fresh deep copy each time it is called, and
	# it is called once here and once in `course_scene` - so the scene has
	# always been holding a DIFFERENT terrain dictionary from the one the
	# ground was built from, and only this one ever receives `cut_index` from
	# `Terrain.index_cut`. Anything asking the scene's copy for a height was
	# therefore being told about the mountain as it would be if the route had
	# never been benched into it, which along the whole racing line is up to
	# `cut_depth` too high.
	#
	# Published rather than returned so the fix is one line at each end and
	# nothing about the build order changes.
	root.set_meta("terrain_cfg", terrain_cfg)
	return root


# --- supports -------------------------------------------------------------


static func _supports(root: Node3D, palette, run: Node3D, cfg: Dictionary,
		scale: float, name: String) -> Array:
	## Local structure under one run, and the ground clearance it measured.
	##
	## ## What is deliberately unchanged
	##
	## `SUPPORT_SPACING`, `KEEL_DROP`, the sample loop and the `clearances`
	## array it returns. Those feed `min_clearance`, `max_clearance` and
	## `buried_piers` in the course metrics, and the metrics are written into
	## `physics_layout.json` - so a presentation pass that moved a pier would
	## be editing physics metadata to make a frame look better. Every pier
	## stands exactly where it stood; only what is built on it changed.
	##
	## ## What changed, and why plates rather than more tubes
	##
	## The review called the trestles loose sticks, and the temptation is to
	## add members. The previous pass already went the other way for a good
	## reason, written down in `_trestle`: a diagonal per level per face is
	## four more tubes in a frame that already has four legs, and at close
	## range that is a tangle rather than a truss. Both notes are correct, and
	## together they say the missing thing is not a member - it is a FLAT. A
	## bundle of cylinders has no plane to catch the key, so it has no
	## highlight, so it has no silhouette at any distance. Gussets, base
	## plates and a web give the same frame flats without adding a single
	## crossing line.
	##
	## And two new kinds, both from the brief:
	##
	##     cantilever    where the uphill bench stands above the keel, the
	##                   bracket comes off the hill instead of a column
	##                   rising past it - which is what an installation on a
	##                   benched route actually does
	##     plate girder  between two adjacent trestles, a web under the keel,
	##                   so a gorge crossing reads as one bridge rather than
	##                   as two towers with track lying across them
	var path: Array = run.get_meta("path")
	var banks: Array = run.get_meta("banks")
	var group := Node3D.new()
	group.name = "Support%s" % name.capitalize()
	root.add_child(group)

	var total: float = V2Forms.path_length(path)
	var count: int = maxi(int(round(total / SUPPORT_SPACING)), 2)
	var graphite = palette.get_material("graphite")
	var deep = palette.get_material("graphite_deep")
	var plate = palette.get_material("graphite_plate_polish")
	var gold = palette.get_material("gold_dark")
	var clearances: Array = []
	# Where each trestle ended up, so the girders can span between them.
	var trestles: Array = []

	for step in count + 1:
		var t := float(step) / float(count)
		var index: int = clampi(int(round(t * float(path.size() - 1))),
			0, path.size() - 1)
		var frame: Basis = V2Forms.banked_basis(path, banks, index)
		var centre: Vector3 = path[index]
		var keel: float = centre.y - KEEL_DROP * scale
		var ground: float = Terrain.height(centre.x, centre.z, cfg)
		var gap: float = keel - ground
		clearances.append(gap)
		if step == 0 or step == count:
			continue

		var pier := Node3D.new()
		pier.name = "Pier%d" % step
		pier.position = Vector3(centre.x, 0.0, centre.z)
		# Piers face along the track so a Y-frame's arms open across it.
		var heading := Vector3(frame.z.x, 0.0, frame.z.z)
		if heading.length_squared() > 1.0e-6:
			pier.rotation.y = atan2(heading.x, heading.z)
		group.add_child(pier)

		if gap < 1.1:
			var plinth := Forms.mesh_node(
				Geometry.rounded_box(Vector3(2.1 * scale, 1.5, 1.5 * scale),
					0.24, 3), deep, "Plinth", false)
			plinth.position.y = keel - 0.65
			pier.add_child(plinth)
			continue

		if gap < 8.0:
			# The bench either side, at the pier's own station. Where the
			# uphill ground stands above the keel the track is running in a
			# cut, and a column rising out of a cut wall is the tell that the
			# support was placed by a rule rather than designed.
			var across := Vector3(frame.x.x, 0.0, frame.x.z).normalized()
			var reach: float = 2.6 * scale
			var a := centre + across * reach
			var b := centre - across * reach
			var ha: float = Terrain.height(a.x, a.z, cfg)
			var hb: float = Terrain.height(b.x, b.z, cfg)
			var uphill: float = 1.0 if ha > hb else -1.0
			var bench: float = maxf(ha, hb)
			if bench > keel - 0.35 * scale and gap < 5.4:
				_cantilever(pier, graphite, plate, gold, keel, bench,
					uphill, reach, scale)
			else:
				_yoke(pier, graphite, plate, gold, keel, ground, gap, scale)
			continue
		_trestle(pier, graphite, deep, plate, gold, keel, ground, gap, scale)
		trestles.append({"at": Vector3(centre.x, keel, centre.z),
			"ground": ground, "gap": gap})
	_girders(group, palette, trestles, scale)
	return clearances


static func _cantilever(pier: Node3D, graphite, plate, gold, keel: float,
		bench: float, uphill: float, reach: float, scale: float) -> void:
	## A bracket off the uphill bench, carrying the keel out over the drop.
	##
	## Three parts and no column: a pad set into the cut face, a pair of
	## raking struts from the pad up to the keel, and a plate knee where they
	## meet. The point is that the load path is visibly into the HILL rather
	## than down to ground the track is flying over, which is the structural
	## reading a benched route should have and the one thing a column under
	## the centreline cannot say.
	var root_x: float = uphill * reach * 0.86
	var pad := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.35 * scale, 1.05, 1.55 * scale),
			0.16, 3), plate, "BenchPad", false)
	pad.position = Vector3(root_x, bench - 0.45, 0.0)
	pier.add_child(pad)

	# Two struts, not one: two members read as a bracket, one reads as a prop.
	for offset in [-0.42, 0.42]:
		var strut := Forms.mesh_node(
			Forms.brace(Vector3(root_x, bench - 0.30, offset * scale),
				Vector3(uphill * 0.30 * scale, keel - 0.06, offset * scale),
				0.20 * scale, 10),
			graphite, "Strut%d" % int(offset * 100.0), false)
		pier.add_child(strut)
	# The knee: a flat, and the only surface on the assembly that faces the
	# key square on.
	var knee := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.9 * scale, 0.70, 0.20 * scale),
			0.09, 3), plate, "Knee", false)
	knee.position = Vector3(root_x * 0.46, lerpf(bench, keel, 0.52), 0.0)
	knee.rotation.z = atan2(keel - bench, -root_x) * 0.9
	pier.add_child(knee)
	var cap := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.0 * scale, 0.26, 0.9 * scale),
			0.10, 3), gold, "Cap", false)
	cap.position.y = keel + 0.02
	pier.add_child(cap)


static func _yoke(pier: Node3D, graphite, plate, gold, keel: float,
		ground: float, gap: float, scale: float) -> void:
	## A Y: one leg into the ground, two arms opening under the channel.
	##
	## The arms and the stem are unchanged in geometry. What is added is a
	## base plate, a collar where the arms spring and a tie between their
	## tips - three flats on an assembly that previously presented none, and
	## the reason a Y-frame at forty units used to read as a bent wire.
	var stem_top: float = keel - gap * 0.42
	var column := Forms.mesh_node(
		Forms.column(gap * 0.58 + 0.6, 0.30 * scale, 0.09), graphite,
		"Stem", false)
	column.position.y = ground - 0.3 + (gap * 0.58 + 0.6) * 0.5
	pier.add_child(column)

	for side in [-1.0, 1.0]:
		var top := Vector3(side * 0.86 * scale, keel + 0.05, 0.0)
		var foot := Vector3(0.0, stem_top, 0.0)
		var arm := Forms.mesh_node(Forms.brace(foot, top, 0.13 * scale),
			graphite, "Arm%s" % ("L" if side < 0.0 else "R"), false)
		pier.add_child(arm)
	# The spring collar: where the two arms leave the stem, which is the one
	# place on a Y that a real fabrication puts a machined part.
	var collar := Forms.mesh_node(
		Geometry.rounded_disc(0.44 * scale, 0.34 * scale, 0.10, 14, 3),
		plate, "Collar", false)
	collar.position.y = stem_top
	pier.add_child(collar)
	# A tie across the arm tips, under the cap. It closes the Y into a frame
	# and gives the assembly a horizontal in silhouette.
	var tie := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.86 * scale, 0.16, 0.22 * scale),
			0.06, 3), plate, "Tie", false)
	tie.position.y = keel - 0.22
	pier.add_child(tie)
	var cap := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.0 * scale, 0.26, 0.7 * scale),
			0.10, 3), gold, "Cap", false)
	cap.position.y = keel + 0.02
	pier.add_child(cap)
	# A square base plate under the round foot: the flat that reads as
	# bolted down rather than as pushed in.
	var base := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.9, 0.24, 1.9), 0.07, 3), plate,
		"BasePlate", false)
	base.position.y = ground - 0.42
	pier.add_child(base)
	var pad := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.5, 0.5, 1.5), 0.18, 3), graphite,
		"Foot", false)
	pad.position.y = ground - 0.2
	pier.add_child(pad)


static func _trestle(pier: Node3D, graphite, deep, plate, gold, keel: float,
		ground: float, gap: float, scale: float) -> void:
	## A braced frame for a real span: four splayed legs and X bracing.
	##
	## The width at the foot is a fraction of the height, so a tall trestle is
	## visibly a *tower of structure* and a short one is a stool. That taper is
	## the whole reason a bridge over a gorge reads as engineered.
	# Stock scaled to the span. At a fixed radius a ten-unit trestle is four
	# hairlines and two diagonals, and a group of them under a viaduct reads
	# as loose sticks rather than as structure - which is what the first pass
	# shipped. A leg on a tall frame is a member, not a wire.
	var stock: float = (0.26 + 0.027 * gap) * scale
	var half_top: float = 1.05 * scale
	var half_foot: float = half_top + gap * 0.22
	var depth: float = 0.70 * scale
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			var top := Vector3(sx * half_top, keel + 0.05, sz * depth)
			var foot := Vector3(sx * half_foot, ground - 0.4,
				sz * (depth + gap * 0.12))
			pier.add_child(Forms.mesh_node(
				Forms.brace(foot, top, stock, 10), graphite,
				"Leg%d%d" % [int(sx), int(sz)], false))
			# A base plate per leg. Four small flats at the feet, which is
			# where the eye looks to decide whether a frame is standing on
			# the ground or stuck into it.
			var shoe := Forms.mesh_node(
				Geometry.rounded_box(Vector3(stock * 3.4, 0.22, stock * 3.4),
					0.06, 3), plate, "Shoe%d%d" % [int(sx), int(sz)], false)
			shoe.position = Vector3(sx * half_foot, ground - 0.46,
				sz * (depth + gap * 0.12))
			pier.add_child(shoe)
	# Horizontal ties at each level, and exactly one diagonal per face over
	# the whole height. A diagonal *per level per face* is four more members
	# in a frame that already has four legs, and at close range the result is
	# a tangle of crossing tubes rather than a truss.
	var levels := maxi(int(gap / 4.6), 1)
	for level in levels:
		var t := (float(level) + 0.62) / float(levels + 0.5)
		var y: float = lerpf(ground - 0.2, keel, t)
		var half: float = lerpf(half_foot, half_top, t)
		for sz in [-1.0, 1.0]:
			pier.add_child(Forms.mesh_node(
				Forms.brace(Vector3(-half, y, sz * depth),
					Vector3(half, y, sz * depth), stock * 0.58, 8),
				deep, "Tie%d%d" % [level, int(sz)], false))
		# A gusset where each tie meets each leg. Four small plates per
		# level, no new crossing lines, and the difference between a bundle
		# of tubes and a fabrication.
		for sx in [-1.0, 1.0]:
			for sz in [-1.0, 1.0]:
				var gusset := Forms.mesh_node(
					Geometry.rounded_box(Vector3(stock * 4.6, stock * 4.6,
						stock * 0.7), 0.05, 2), plate,
					"Gusset%d%d%d" % [level, int(sx), int(sz)], false)
				gusset.position = Vector3(sx * half, y, sz * depth)
				pier.add_child(gusset)
	for sz in [-1.0, 1.0]:
		pier.add_child(Forms.mesh_node(
			Forms.brace(Vector3(-half_foot, ground - 0.1, sz * depth),
				Vector3(half_top, keel - 0.1, sz * depth), stock * 0.48, 8),
			deep, "Diagonal%d" % int(sz), false))
	# The head: a solid web between the leg tops, under the cap. One flat at
	# the top of the frame, where the frame meets the thing it carries, and
	# the surface that finally gives a trestle a highlight of its own.
	var web := Forms.mesh_node(
		Geometry.rounded_box(Vector3(half_top * 2.0, 0.72 * scale,
			depth * 1.5), 0.08, 3), plate, "Web", false)
	web.position.y = keel - 0.48 * scale
	pier.add_child(web)
	var cap := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.3 * scale, 0.3, 1.5 * scale),
			0.12, 3), gold, "Cap", false)
	cap.position.y = keel + 0.04
	pier.add_child(cap)


static func _girders(group: Node3D, palette, trestles: Array,
		scale: float) -> void:
	## A plate girder between adjacent trestles: the bridge frames.
	##
	## Two tall frames with track lying across the top of them are two
	## towers. The same two with a web spanning between them are a bridge, and
	## a bridge is the strongest silhouette a course over a gorge can have -
	## which is the brief's "occasional bridge frames", and also what the
	## viaduct sprint into the finish was missing.
	##
	## A plate girder rather than a truss, on purpose. A truss between two
	## trestles is another dozen crossing tubes in the part of the frame that
	## already has the most, and the note in `_trestle` about tangles applies
	## twice as hard to the span. A web plate has one edge, casts one shadow,
	## and is what a real span of this proportion is built from anyway.
	##
	## Hung UNDER the keel and never over it. The brief's camera rule - that
	## supports must not cross the action area - is a rule about geometry
	## before it is a rule about framing: anything above the running surface
	## can occlude a racer from some camera, and the fix is not to build it.
	if trestles.size() < 2:
		return
	var web = palette.get_material("graphite_plate_polish")
	var chord = palette.get_material("graphite_deep")
	for index in range(trestles.size() - 1):
		var a: Dictionary = trestles[index]
		var b: Dictionary = trestles[index + 1]
		var from: Vector3 = a["at"]
		var to: Vector3 = b["at"]
		var span := from.distance_to(to)
		# Only between neighbours that are actually a pair. Two trestles ten
		# units apart are a span; the same two twenty-five apart are two
		# separate structures, and a plate between them is a fence.
		if span > SUPPORT_SPACING * 1.6 or span < 1.0:
			continue
		var mid: Vector3 = (from + to) * 0.5
		# The web's depth follows the shallower of the two towers, so a span
		# never hangs lower than the ground it crosses.
		var drop: float = clampf(minf(float(a["gap"]), float(b["gap"]))
			* 0.30, 0.6, 2.4) * scale
		var bridge := Node3D.new()
		bridge.name = "Girder%d" % index
		bridge.position = mid
		bridge.rotation.y = atan2(to.x - from.x, to.z - from.z)
		group.add_child(bridge)
		for side in [-1.0, 1.0]:
			var suffix := "L" if side < 0.0 else "R"
			var sheet := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.16 * scale, drop, span),
					0.05, 2), web, "Web%s" % suffix, false)
			sheet.position = Vector3(side * 0.86 * scale,
				-drop * 0.5 - 0.30 * scale, 0.0)
			bridge.add_child(sheet)
			# A bottom chord along each web's lower edge. It is what stops a
			# plate hanging in space reading as a card.
			var rail := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.34 * scale, 0.20 * scale,
					span), 0.07, 2), chord, "Chord%s" % suffix, false)
			rail.position = Vector3(side * 0.86 * scale,
				-drop - 0.34 * scale, 0.0)
			bridge.add_child(rail)


# --- markers --------------------------------------------------------------


static func _markers(root: Node3D, palette, table: Dictionary,
		detail: String) -> void:
	## Blockout volumes at the six race moments.
	##
	## Deliberately plain: a layout study that dresses its modules is a study of
	## the dressing. Each marker is sized to the footprint the real module will
	## need, so a shape that has no room for its own finish arena fails here
	## rather than after a week of detailing.
	if detail != "block":
		return
	var nodes: Dictionary = table["nodes"]
	var group := Node3D.new()
	group.name = "Markers"
	root.add_child(group)

	var plan := [
		["start", Vector3(6.2, 1.3, 3.0), "pearl_shell", "lit_cyan"],
		["mix", Vector3(3.4, 1.1, 2.6), "pearl_shade", "lit_violet"],
		["obstacle", Vector3(4.6, 1.8, 4.0), "orange_machine", "lit_orange"],
		["split", Vector3(4.2, 1.2, 3.2), "graphite_soft", "lit_white"],
		["merge", Vector3(3.6, 1.0, 3.0), "graphite_soft", "lit_gold"],
		["finish", Vector3(8.4, 1.4, 7.0), "pearl_warm", "lit_gold_wash"],
	]
	for entry in plan:
		var name := str(entry[0])
		if not nodes.has(name):
			continue
		var size: Vector3 = entry[1]
		var pad := Node3D.new()
		pad.name = name.capitalize()
		pad.position = nodes[name]
		group.add_child(pad)
		var body := Forms.mesh_node(
			Geometry.rounded_box(size, 0.30, 3),
			palette.get_material(str(entry[2])), "Body")
		body.position.y = -size.y * 0.5 + 0.10
		pad.add_child(body)
		var crown := Forms.mesh_node(
			Geometry.rounded_box(Vector3(size.x * 0.92, 0.16,
				size.z * 0.92), 0.07, 3),
			palette.get_material(str(entry[3])), "Crown", false)
		crown.position.y = 0.24
		pad.add_child(crown)


static func _modules(root: Node3D, palette, table: Dictionary,
		detail: String) -> void:
	## The six authored race moments, each placed on its anchor and yawed to
	## the direction of travel there.
	##
	## Nothing in `course_modules` or `course_finish` knows a world coordinate.
	## They are built in a frame where +Z is downhill and handed the couple of
	## points they have to meet exactly - where the first run begins, where the
	## two branches arrive, where the last run ends - already transformed into
	## that frame. Re-route the course and every module follows it.
	if detail == "block":
		return
	var nodes: Dictionary = table["nodes"]
	var group := Node3D.new()
	group.name = "Modules"
	root.add_child(group)

	var launch: Array = root.get_meta("launch_path")
	var final_run: Array = root.get_meta("final_path")
	var blue: Array = root.get_meta("blue_path")
	var orange: Array = root.get_meta("orange_path")

	var start_at: Vector3 = nodes["start"]
	var start_yaw := _yaw_to(start_at, launch[0])
	group.add_child(_placed(Modules.start(palette,
		_to_local(start_at, start_yaw, launch[0])), start_at, start_yaw))

	group.add_child(_placed(Modules.mixer(palette), nodes["mix"],
		_yaw_at(launch, launch.size() - 2)))

	# Yawed to the *track under it*, not to the gap between two runs. Those
	# two runs now share a control point exactly - which is what closed the
	# joints - so the delta between them is zero and the module came out
	# pointing down +Z while the channel ran across it.
	group.add_child(_placed(Modules.obstacle(palette), nodes["obstacle"],
		_yaw_near(root, table, nodes["obstacle"])))

	var split_at: Vector3 = nodes["split"]
	group.add_child(_placed(Modules.split(palette), split_at,
		_yaw_to(split_at, (blue[0] + orange[0]) * 0.5)))

	var merge_at: Vector3 = nodes["merge"]
	var merge_yaw := _yaw_to(merge_at, final_run[0])
	group.add_child(_placed(Modules.merge(palette,
		_to_local(merge_at, merge_yaw, blue[-1]),
		_to_local(merge_at, merge_yaw, orange[-1]),
		_to_local(merge_at, merge_yaw, final_run[0])), merge_at, merge_yaw))

	var finish_at: Vector3 = nodes["finish"]
	var finish_yaw := _yaw_at(final_run, final_run.size() - 2)
	group.add_child(_placed(FinishArena.build(palette,
		_to_local(finish_at, finish_yaw, final_run[-1])),
		finish_at, finish_yaw))


static func _placed(node: Node3D, at: Vector3, yaw: float) -> Node3D:
	node.position = at
	node.rotation.y = yaw
	return node


static func _yaw_to(from: Vector3, to: Vector3) -> float:
	var delta := to - from
	if absf(delta.x) < 1.0e-6 and absf(delta.z) < 1.0e-6:
		return 0.0
	return atan2(delta.x, delta.z)


static func _yaw_near(root: Node3D, table: Dictionary,
		point: Vector3) -> float:
	## The direction of travel at the nearest sample of any run.
	var best := 1.0e9
	var yaw := 0.0
	for entry in table["runs"]:
		var path: Array = root.get_meta("%s_path"
			% str((entry as Dictionary)["name"]))
		for index in path.size():
			var distance: float = (path[index] as Vector3).distance_to(point)
			if distance < best:
				best = distance
				yaw = _yaw_at(path, index)
	return yaw


static func _yaw_at(path: Array, index: int) -> float:
	var at: int = clampi(index, 0, path.size() - 2)
	return _yaw_to(path[at], path[at + 1])


static func _to_local(origin: Vector3, yaw: float, point: Vector3) -> Vector3:
	## `point` in the frame of a node placed at `origin` and yawed by `yaw`.
	var delta := point - origin
	var c := cos(yaw)
	var s := sin(yaw)
	return Vector3(delta.x * c - delta.z * s, delta.y,
		delta.x * s + delta.z * c)


static func _field(root: Node3D, palette, table: Dictionary) -> void:
	## Eight racers spread along the course, so scale is readable from any shot.
	var field := Node3D.new()
	field.name = "Field"
	root.add_child(field)
	var sphere := SphereMesh.new()
	sphere.radius = Layout.MARBLE_RADIUS
	sphere.height = Layout.MARBLE_RADIUS * 2.0
	sphere.radial_segments = 24
	sphere.rings = 12

	# Three abreast is the claim the brief makes about the hero channel's
	# width, so the field is placed in threes and the picture has to support it
	# rather than a note asserting it.
	#
	# ## Why the phases are a table and not a formula
	#
	# Two packs at 0.10 and 0.60 leave a third of every run without a racer on
	# it, and a section camera aimed into one of those gaps photographs empty
	# channel - which is the brief's first camera failure and the reason the
	# committed finish frame has nothing arriving in it. A camera cannot solve
	# that: the only fix is that the display field has a pack wherever a shot
	# is worth taking.
	#
	# So the stations come from the shot list rather than from an interval.
	# Three packs at 0.06, 0.40 and 0.68 put a pack within a few hundredths of
	# every candidate's aim point, and the sprint gets a fourth at 0.96 so the
	# finish has a field in its mouth. Display only - `travellers` is read by
	# `course_scene.set_time` to move them at a constant rate and by nothing
	# else, it is not written to the physics dump, and no lane, phase or count
	# here is a claim about a race.
	var stations := [0.06, 0.40, 0.68]
	var sprint_stations := [0.06, 0.40, 0.68, 0.96]
	var travellers: Array = []
	var index := 0
	for entry in table["runs"]:
		var spec: Dictionary = entry
		var name := str(spec["name"])
		var narrow: bool = float(spec["scale"]) < 0.9
		var lanes := [-0.40, 0.0, 0.40] if narrow else [-0.54, 0.0, 0.54]
		var packs: Array = sprint_stations if str(spec["role"]) == "sprint" \
			else stations
		for pack in packs.size():
			for at in lanes.size():
				var node := MeshInstance3D.new()
				node.name = "Racer%d" % index
				node.mesh = sphere
				node.material_override = palette.marble(index)
				field.add_child(node)
				travellers.append({"node": node.name, "run": name,
					"lane": float(lanes[at]),
					"phase": fposmod(float(packs[pack])
						+ 0.055 * float(at), 1.0)})
				index += 1
	root.set_meta("travellers", travellers)


# --- metrics --------------------------------------------------------------


static func _metrics(table: Dictionary, length: float, clearances: Array,
		centreline: Array) -> Dictionary:
	var nodes: Dictionary = table["nodes"]
	var lo := Vector3(1.0e9, 1.0e9, 1.0e9)
	var hi := -lo
	for point in centreline:
		lo = Vector3(minf(lo.x, (point as Vector3).x),
			minf(lo.y, (point as Vector3).y), minf(lo.z, (point as Vector3).z))
		hi = Vector3(maxf(hi.x, (point as Vector3).x),
			maxf(hi.y, (point as Vector3).y), maxf(hi.z, (point as Vector3).z))
	var worst := 1.0e9
	var tallest := -1.0e9
	var buried := 0
	for gap in clearances:
		worst = minf(worst, float(gap))
		tallest = maxf(tallest, float(gap))
		if float(gap) < -0.2:
			buried += 1
	var start: Vector3 = nodes["start"]
	var finish: Vector3 = nodes["finish"]
	return {
		"length": length,
		"drop": hi.y - lo.y,
		"span_x": hi.x - lo.x,
		"span_z": hi.z - lo.z,
		"start_to_finish": start.distance_to(finish),
		"min_clearance": worst,
		"max_clearance": tallest,
		"buried_piers": buried,
		"mean_grade_deg": rad_to_deg(atan((hi.y - lo.y) / maxf(length, 1.0))),
	}
