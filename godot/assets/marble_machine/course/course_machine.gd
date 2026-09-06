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

const KEEL_DROP := 0.98         # v2_track's keel bottom, in profile units
const SUPPORT_SPACING := 5.6
const RACERS := 8

# Edge-light key per run role: the colour story read along the course rather
# than down a tower. Cyan from the line, violet through the middle, the two
# branch identities at the choice, gold from the merge to the flag.
const EDGE_LIGHTS := {
	"descent": "lit_cyan_line_hero",
	"long": "lit_cyan_line_hero",
	"branch": "neon_blue",
	"sprint": "lit_gold_line",
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
		var light := str(EDGE_LIGHTS.get(role, "lit_cyan_line_hero"))
		var shell := "pearl_shell"
		var floor_key := "running_polished"
		var guard := "acrylic_guard"
		if name == "blue":
			shell = "blue_machine"
			floor_key = "running_blue"
			guard = "acrylic_blue"
		elif name == "orange":
			shell = "orange_machine"
			floor_key = "running_orange"
			guard = "acrylic_amber"
			light = "lit_orange_line"
		elif role == "sprint":
			shell = "pearl_warm"
			floor_key = "running_warm"
			guard = "acrylic_gold"

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

	for entry in runs.get_children():
		var run: Node3D = entry
		var spec: Dictionary = _spec_for(table, run.name.to_lower())
		clearances.append_array(_supports(root, palette, run, terrain_cfg,
			float(spec["scale"]), str(spec["name"])))

	_markers(root, palette, table, detail)
	_field(root, palette, table)
	Terrain.scatter(ground, palette, terrain_cfg,
		int(options.get("rocks", 46)), centreline, 5.4)

	root.set_meta("metrics", _metrics(table, total_length, clearances,
		centreline))
	return root


static func _spec_for(table: Dictionary, name: String) -> Dictionary:
	for entry in table["runs"]:
		if str((entry as Dictionary)["name"]) == name:
			return entry
	push_error("course_machine: no run named '%s'" % name)
	return table["runs"][0]


# --- supports -------------------------------------------------------------


static func _supports(root: Node3D, palette, run: Node3D, cfg: Dictionary,
		scale: float, name: String) -> Array:
	## Local structure under one run, and the ground clearance it measured.
	var path: Array = run.get_meta("path")
	var banks: Array = run.get_meta("banks")
	var group := Node3D.new()
	group.name = "Support%s" % name.capitalize()
	root.add_child(group)

	var total: float = V2Forms.path_length(path)
	var count: int = maxi(int(round(total / SUPPORT_SPACING)), 2)
	var graphite = palette.get_material("graphite")
	var deep = palette.get_material("graphite_deep")
	var gold = palette.get_material("gold_dark")
	var clearances: Array = []

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
			_yoke(pier, graphite, gold, keel, ground, gap, scale)
			continue
		_trestle(pier, graphite, deep, gold, keel, ground, gap, scale)
	return clearances


static func _yoke(pier: Node3D, graphite, gold, keel: float, ground: float,
		gap: float, scale: float) -> void:
	## A Y: one leg into the ground, two arms opening under the channel.
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
	var cap := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.0 * scale, 0.26, 0.7 * scale),
			0.10, 3), gold, "Cap", false)
	cap.position.y = keel + 0.02
	pier.add_child(cap)
	var pad := Forms.mesh_node(
		Geometry.rounded_box(Vector3(1.5, 0.5, 1.5), 0.18, 3), graphite,
		"Foot", false)
	pad.position.y = ground - 0.2
	pier.add_child(pad)


static func _trestle(pier: Node3D, graphite, deep, gold, keel: float,
		ground: float, gap: float, scale: float) -> void:
	## A braced frame for a real span: four splayed legs and X bracing.
	##
	## The width at the foot is a fraction of the height, so a tall trestle is
	## visibly a *tower of structure* and a short one is a stool. That taper is
	## the whole reason a bridge over a gorge reads as engineered.
	var half_top: float = 0.95 * scale
	var half_foot: float = half_top + gap * 0.20
	var depth: float = 0.62 * scale
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			var top := Vector3(sx * half_top, keel + 0.05, sz * depth)
			var foot := Vector3(sx * half_foot, ground - 0.4,
				sz * (depth + gap * 0.10))
			pier.add_child(Forms.mesh_node(
				Forms.brace(foot, top, 0.145 * scale), graphite,
				"Leg%d%d" % [int(sx), int(sz)], false))
	var levels := maxi(int(gap / 3.2), 1)
	for level in levels:
		var t := (float(level) + 0.55) / float(levels + 0.4)
		var y: float = lerpf(ground - 0.2, keel, t)
		var half: float = lerpf(half_foot, half_top, t)
		for sz in [-1.0, 1.0]:
			pier.add_child(Forms.mesh_node(
				Forms.brace(Vector3(-half, y, sz * depth),
					Vector3(half, y, sz * depth), 0.085 * scale),
				deep, "Tie%d%d" % [level, int(sz)], false))
		pier.add_child(Forms.mesh_node(
			Forms.brace(Vector3(-half, y - 1.1, -depth),
				Vector3(half, y + 1.1, depth), 0.065 * scale),
			deep, "Brace%d" % level, false))
	var cap := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.3 * scale, 0.3, 1.5 * scale),
			0.12, 3), gold, "Cap", false)
	cap.position.y = keel + 0.04
	pier.add_child(cap)


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

	var travellers: Array = []
	var runs: Array = table["runs"]
	var index := 0
	for entry in runs:
		var spec: Dictionary = entry
		var name := str(spec["name"])
		# Three abreast on the hero runs is the claim the brief makes about
		# width, so the field is placed in threes and the picture has to
		# support it rather than the note asserting it.
		var lanes := [0.0] if float(spec["scale"]) < 0.9 else [-0.52, 0.0, 0.52]
		for lane in lanes:
			var node := MeshInstance3D.new()
			node.name = "Racer%d" % index
			node.mesh = sphere
			node.material_override = palette.marble(index)
			field.add_child(node)
			travellers.append({"node": node.name, "run": name,
				"lane": lane,
				"phase": fmod(0.16 + 0.37 * float(index), 1.0)})
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
	var buried := 0
	for gap in clearances:
		worst = minf(worst, float(gap))
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
		"buried_piers": buried,
		"mean_grade_deg": rad_to_deg(atan((hi.y - lo.y) / maxf(length, 1.0))),
	}
