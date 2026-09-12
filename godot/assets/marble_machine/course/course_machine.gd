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

## Where the acrylic rail is raised, and by how much. **The same table as
## `sloped.course.GUARD_BOOSTS`, and it has to stay the same table**: the
## physics collider carries these windows, so a render without them draws a
## marble bouncing off nothing.
##
## `[extra, a, b, c, d]` in profile units - authored height before sample `a`,
## eased to `authored + extra` by `b`, held to `c`, eased back by `d`.
## `tools/sloped_escape_trace.py` measured the three stretches: marbles at 16 to
## 31 layout units per second going over the top of the 0.26 rail, their centres
## above the containment and outside the rail's face, on the launch's plunge and
## in leg1's and leg2's banked hairpins.
const GUARD_BOOSTS := {
	"launch": [0.50, 12, 24, 70, 84],
	"leg1": [0.50, 46, 58, 100, 110],
	"leg2": [0.50, 60, 72, 106, 116],
	# orange's hairpin: the smallest rail on the course - a branch is at
	# BRANCH_SCALE 0.82 throughout - on its tightest corner, radius 2.74 at
	# `orange[18]` and balanced at 20.5 wu/s under 32 degrees of bank. The
	# field rode over the top of it for sixteen consecutive samples.
	"orange": [0.50, 4, 12, 38, 46],
}

## Where a run's roll may not unwind faster than the drop pays for. **The same
## table as `sloped.course.BANK_SLEWS`, and it has to stay the same table**: the
## collider is swept along this roll, so a render without it draws marbles
## cornering on a surface that is not the one they ride.
##
## `[first sample, last sample, margin]` - between those samples the roll only
## unwinds as fast as `margin` of the local drop allows, so neither channel edge
## ever rises along the run. leg2's inflection unwinds about five degrees a
## sample against a 10% fall, which eats 89.7% of the drop and leaves a pocket
## on the outside; it held 41 of the 56 non-finishers in the 600-race benchmark.
## **blue's tail carries the same defect and it was never surveyed**, because
## `tools/sloped_pocket_survey.py` walks the four chain runs and the sprint only.
## blue's roll reverses from -17.45 degrees at sample 89 to +10.50 at 99 while
## the centreline falls 0.164 layout units; the reversal costs 0.372, so its
## east edge climbs 0.3013 where its centre descends throughout. That climb tops
## out at sample 98 and `blue[100]` is the loss site - 8 of V1.11's 24 remaining
## non-finishers, and where V1 lost 319 of its 747 marbles.
## Orange's covers the **whole** run rather than a window, and that is what
## makes it work: over its tail alone the authored roll costs 3.96 times the
## drop it has, so a rate cap started there lags and never catches up, while
## over the whole run the ratio is 0.82. Its basins are the deepest on the
## course - 0.9223 at the channel edge against leg2's 0.0685 - and the bank
## extreme is still preserved exactly, at 32 degrees.
const BANK_SLEWS := {
	"leg2": [98, 112, 1.0],
	"blue": [84, 117, 1.0],
	"orange": [0, 117, 1.0],
}

## Where a rail is **opened**, and how far. **The same table as the windows
## `sloped.course` hands `TrackRun`, and it has to stay the same table**: the
## collider has a gap at every one of these, so a render without them draws a
## full-height acrylic wall exactly where a marble crosses.
##
## `[side, a, b, c, d]` plus an optional floor fraction - full height at or
## before `a`, eased down by `b`, held to `c`, eased back to full by `d`. A
## side of `1.0` is the east rail, `-1.0` the west, `0.0` both.
##
## * **leg3** is the fork. Its east guard stands at `sloped.course.FORK_CREST`
##   of full height over `sloped.joins.FORK_GUARD_WINDOW`, which is the
##   *sorting crest* rather than a hole: a marble crosses into orange on its
##   own momentum against leg3's bank, and at 0.12 the crest is the threshold
##   that decides. Drawing it full height is the mismatch section 19 of the
##   V1.15 brief names.
## * **blue's tail and the sprint** stand inside the merge apron's roof, and a
##   rail inside a roofed apron leaves a ledge along its own top - V1 lost 319
##   of its 747 marbles resting on one. The sprint's window closes at sample 14
##   rather than 9 because the apron's shoulder is still wide enough to hold a
##   marble at sample 11; see `sloped.course.MERGE_GUARD_WINDOW`.
##
## The two leads and the merge lead carry windows too, and they are absent here
## for the reason every join is: this layout table has the seven authored runs
## and no join geometry at all.
const OPEN_SIDES := {
	"leg3": [1.0, 81, 82, 90, 92, 0.12],
	"blue": [0.0, 111, 113, 118, 119],
	"final": [0.0, -1, 0, 12, 14],
}
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
	"launch": "lit_cyan_line_hero",
	"leg1": "lit_cyan_line_hero",
	"leg2": "lit_cyan_line_hero",
	"leg3": "neon_violet_hero",
	"blue": "neon_blue",
	"orange": "lit_orange_line",
	"final": "lit_gold_line",
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
		var light := str(EDGE_LIGHTS.get(name, "lit_cyan_line_hero"))
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
			"guard_boost": GUARD_BOOSTS.get(name, []),
			"bank_slew": BANK_SLEWS.get(name, []),
			# leg3's window is the fork, which only exists on the two-route
			# course; `routes` is "blue" for a render of the through route
			# alone, exactly as `sloped.course.sloped_course` reads it.
			"open_side": ([] if (name == "leg3" and str(options.get("routes",
				"both")) == "blue") else OPEN_SIDES.get(name, [])),
			"ribs": detail != "block",
		})
		runs.add_child(run)
		# The node's own name is display text; this is the key.
		run.set_meta("run_name", name)
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

	# **By the run's own recorded name, not by its node name.** `Track.build` is
	# handed `name.capitalize()`, and GDScript's `capitalize()` puts a space
	# before a digit - so "leg1" comes back as "Leg 1" and `to_lower()` gives
	# "leg 1", which matches no run. `_spec_for` then pushed an error and fell
	# back to `table["runs"][0]`, so every run whose name ends in a digit got
	# the **launch's** profile scale and label for its supports. Layout B has
	# three of them.
	for entry in runs.get_children():
		var run: Node3D = entry
		var spec: Dictionary = _spec_for(table, str(run.get_meta("run_name", "")))
		clearances.append_array(_supports(root, palette, run, terrain_cfg,
			float(spec["scale"]), str(spec["name"])))

	_markers(root, palette, table, detail)
	_modules(root, palette, table, detail, options.get("start_contract", {}))
	_field(root, palette, table)
	# Two scatters at two scales. The large one reads at a hundred units and
	# the small one at ten, and a section shot is framed at ten - one pass at
	# a single size leaves the near ground smooth in exactly the frames where
	# the ground is a third of the picture.
	Terrain.scatter(ground, palette, terrain_cfg,
		int(options.get("rocks", 64)), centreline, 5.4)
	Terrain.scatter(ground, palette, terrain_cfg,
		int(options.get("pebbles", 110)), centreline, 3.1, 0.34)
	if detail != "block":
		Dressing.build(root, palette, terrain_cfg, centreline,
			table["nodes"])

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
	# Stock scaled to the span. At a fixed radius a ten-unit trestle is four
	# hairlines and two diagonals, and a group of them under a viaduct reads
	# as loose sticks rather than as structure - which is what the first pass
	# shipped. A leg on a tall frame is a member, not a wire.
	var stock: float = (0.22 + gap * 0.023) * scale
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
	for sz in [-1.0, 1.0]:
		pier.add_child(Forms.mesh_node(
			Forms.brace(Vector3(-half_foot, ground - 0.1, sz * depth),
				Vector3(half_top, keel - 0.1, sz * depth), stock * 0.48, 8),
			deep, "Diagonal%d" % int(sz), false))
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


static func _modules(root: Node3D, palette, table: Dictionary,
		detail: String, contract: Dictionary = {}) -> void:
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

	# **The start comes from the physics contract when one is supplied.**
	# `sloped.trapdoor.ShuffleFloor` stands `lift` = 3.93 layout units above the
	# authored node and is a mixing drum rather than a fan pod, so a render that
	# puts the pod on the node draws the field hanging in mid-air - which is
	# what every video shipped since V1.9 did. Without a contract this still
	# builds the V1 pod on the node, which is what keeps the layout proof's own
	# committed frames reproducing.
	if contract.is_empty():
		var start_at: Vector3 = nodes["start"]
		var start_yaw := _yaw_to(start_at, launch[0])
		group.add_child(_placed(Modules.start(palette,
			_to_local(start_at, start_yaw, launch[0])), start_at, start_yaw))
	else:
		var origin: Array = contract["origin"]
		var at := Vector3(float(origin[0]), float(origin[1]), float(origin[2]))
		var yaw := deg_to_rad(float(contract["yaw_deg"]))
		group.add_child(_placed(Modules.shuffle_start(palette, contract), at, yaw))

	# The mixer and the shuffle wheel stand on the *launch* run's own samples,
	# not on the recorded `mix` node, because that is where the physics has
	# them - and a drawn part in the wrong place is a marble bouncing off
	# nothing.
	#
	# V1 put the stud row at `mix`, 1.2 units into leg1.
	# `docs/sloped_race_v11.md` records why it moved: at the leg1 seam the
	# field arrives at 50 wu/s and a stud levers a marble out of the channel,
	# while at launch sample 5 it arrives at 13 and the same stud deflects it.
	# These two numbers are `sloped.course.MIXER_SAMPLE` and `SHUFFLE_SAMPLE`,
	# and `tests/test_sloped_render.py` asserts the three agree.
	var mixer_sample := 5
	var shuffle_sample := 32
	group.add_child(_placed(Modules.mixer(palette), launch[mixer_sample],
		_yaw_at(launch, mixer_sample)))
	group.add_child(_placed(Modules.shuffle(palette), launch[shuffle_sample],
		_yaw_at(launch, shuffle_sample)))

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
	# rather than a note asserting it. Two packs per run, half a lap apart, so
	# that a camera anywhere on two hundred and thirty units of course has
	# racers in frame - this is a display field, not a race.
	var travellers: Array = []
	var index := 0
	for entry in table["runs"]:
		var spec: Dictionary = entry
		var name := str(spec["name"])
		var narrow: bool = float(spec["scale"]) < 0.9
		var lanes := [-0.40, 0.0, 0.40] if narrow else [-0.54, 0.0, 0.54]
		for pack in 2:
			for at in lanes.size():
				var node := MeshInstance3D.new()
				node.name = "Racer%d" % index
				node.mesh = sphere
				node.material_override = palette.marble(index)
				field.add_child(node)
				travellers.append({"node": node.name, "run": name,
					"lane": float(lanes[at]),
					"phase": fposmod(0.10 + 0.5 * float(pack)
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
