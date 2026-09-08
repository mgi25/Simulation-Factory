extends Node3D

## The sloped-course lab scene. One layout, one world, one camera rig.
##
## A fourth lab, and an edit to none of the three before it: `hero_scene.gd`,
## `track_lab_scene.gd` and `lab_scene.gd` are untouched, so every proof already
## committed on the earlier branches still reproduces.
##
## ## Shots are derived, not typed
##
## A course is a route through a world, so the useful camera positions are
## *along* it. Every shot names a point on the route - a module anchor, or a
## fraction along a named run - and gives an elevation, a bearing relative to
## the track's own heading at that point, and a vertical extent. The rig then
## works out where to stand. That is what lets the same seven-shot table serve
## three structurally different layouts, and it is what stops a section camera
## quietly becoming another view of the whole course.

const Palette := preload("res://assets/marble_machine/lab_palette.gd")
const World := preload("res://assets/marble_machine/course/course_world.gd")
const Machine := preload("res://assets/marble_machine/course/course_machine.gd")
const Layout := preload("res://assets/marble_machine/course/course_layout.gd")
const Track := preload("res://assets/marble_machine/v2/v2_track.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Terrain := preload("res://assets/marble_machine/course/course_terrain.gd")
const Style := preload("res://assets/marble_machine/course/course_style.gd")

# at: ["node", name] or ["path", run, t]. `bearing` is measured from the
# track's own forward direction at the aim point - 0 looks up the course from
# in front of it, 90 is a side tracking position, 180 follows from behind.
static var SHOTS := {
	"hero": {"at": ["hero"], "extent": 0.0, "fov": 0.0, "elevation": 0.0,
		"bearing": 0.0},
	"phone": {"at": ["hero"], "extent": 0.0, "fov": 0.0, "elevation": 0.0,
		"bearing": 0.0},
	"start": {"at": ["node", "start"], "extent": 12.6, "fov": 34.0,
		"elevation": 18.0, "bearing": 26.0},
	"descent": {"at": ["path", "launch", 0.60], "extent": 14.0, "fov": 36.0,
		"elevation": 12.0, "bearing": 42.0},
	# Along the track, not across it. A side-on shot of a long straight shows
	# a line; a shot down its axis shows a road running away into the hill,
	# which is the only framing that makes "long" a fact rather than a claim.
	"long_track": {"at": ["path", "leg2", 0.34], "extent": 18.0, "fov": 36.0,
		"elevation": 10.0, "bearing": 16.0},
	"obstacle": {"at": ["node", "obstacle"], "extent": 9.5, "fov": 34.0,
		"elevation": 14.0, "bearing": 44.0},
	# Added for the style lock, and additive: a lens whose whole job is to
	# photograph the cross-section. Every other shot in this table is framed
	# on a race moment, and at a bearing of sixteen to forty-four degrees the
	# surface facing the camera is the channel's *outer shell wall* - so a
	# comparison of running-surface materials made from any of them is a
	# comparison of the one surface that never changes. High and well off the
	# axis, this one sees into the cradle, across the lip, along the guard and
	# under the keel at once.
	"material": {"at": ["path", "leg2", 0.46], "extent": 6.6, "fov": 32.0,
		"elevation": 25.0, "bearing": 58.0},
	"underside": {"at": ["path", "leg1", 0.52], "extent": 9.0, "fov": 32.0,
		"elevation": -4.0, "bearing": 74.0},
	"split": {"at": ["node", "split"], "extent": 15.0, "fov": 34.0,
		"elevation": 17.0, "bearing": 24.0},
	"merge": {"at": ["node", "merge"], "extent": 14.0, "fov": 34.0,
		"elevation": 15.0, "bearing": 32.0},
	"final_run": {"at": ["path", "final", 0.46], "extent": 24.0, "fov": 36.0,
		"elevation": 13.0, "bearing": 40.0},
	"finish": {"at": ["node", "finish"], "extent": 24.0, "fov": 34.0,
		"elevation": 21.0, "bearing": 34.0},
}

# The motion proof's cut list. `shot` reuses a still's lens and animates the
# orbit and dolly across the cut; `follow` walks the aim along a named run and
# carries the camera with it. Explicitly not an orbit of the whole course - the
# brief's own rule, and the right one: a course this long has to be *travelled*
# by the camera or its length is a claim rather than an experience.
const SEQUENCE := [
	{"shot": "hero", "seconds": 0.9, "orbit": [-3.0, 3.0],
		"dolly": [0.05, -0.02]},
	{"shot": "start", "seconds": 1.2, "orbit": [-9.0, 5.0],
		"dolly": [0.12, -0.05]},
	{"follow": "leg1", "seconds": 1.5, "t": [0.16, 0.68], "extent": 11.5,
		"fov": 36.0, "elevation": 15.0, "bearing": 164.0},
	{"follow": "leg2", "seconds": 1.2, "t": [0.18, 0.70], "extent": 15.0,
		"fov": 34.0, "elevation": 17.0, "bearing": 74.0},
	{"shot": "obstacle", "seconds": 0.9, "orbit": [-11.0, 6.0],
		"dolly": [0.07, -0.03]},
	{"shot": "split", "seconds": 1.0, "orbit": [9.0, -9.0],
		"dolly": [0.06, -0.06]},
	{"shot": "finish", "seconds": 1.3, "orbit": [-13.0, 6.0],
		"dolly": [0.16, -0.07]},
]

const DEFAULT_SHOT := "hero"

var _palette
var _camera: Camera3D
var _shot := DEFAULT_SHOT
var _layout := "a"
var _no_glow := false
var _course: Node3D
var _table: Dictionary
var _travellers: Array = []
var _orbit := 0.0
var _dolly := 0.0
var _fitted: Dictionary = {}
var _sequenced := false
var _style: Dictionary = {}


func _ready() -> void:
	var options := _options()
	_layout = str(options.get("layout", "a"))
	_shot = str(options.get("shot", DEFAULT_SHOT))
	_no_glow = str(options.get("no-glow", "")) != ""
	_sequenced = str(options.get("sequence", "")) != ""
	if not SHOTS.has(_shot):
		push_error("course_scene: unknown shot '%s'" % _shot)
		_shot = DEFAULT_SHOT

	# Shadow quality set here rather than in `project.godot`, so the earlier
	# labs' committed frames keep reproducing byte for byte from this branch.
	# A course a hundred and eighty units long puts far more world inside one
	# cascade than a tower did, and at the default atlas the terrace lips came
	# back as a row of sawteeth across the mountainside.
	RenderingServer.directional_shadow_atlas_set_size(8192, false)
	RenderingServer.directional_soft_shadow_filter_set_quality(
		RenderingServer.SHADOW_QUALITY_SOFT_HIGH)

	_palette = Palette.new("tower")
	_table = Layout.table(_layout)
	# Every retuned surface is seeded into the palette before a single module
	# asks for one, so the style reaches the whole machine without any asset
	# knowing a variant exists. With no `--style/--track/...` option this is a
	# no-op and the frame is the one this branch inherited.
	_style = Style.options(options)
	Style.apply(_palette, _style)
	if Style.styled(_style):
		print("style: %s" % Style.label(_style))

	var world_env := WorldEnvironment.new()
	world_env.name = "WorldEnvironment"
	world_env.environment = World.build_environment(_no_glow)
	Style.tune_environment(world_env.environment, str(_style["env"]))
	add_child(world_env)

	World.build_lights(self)
	Style.tune_lights(self, str(_style["env"]))
	var world := World.build(_palette)
	Style.world_extras(world, _palette, str(_style["env"]))
	add_child(world)

	_course = Machine.build(_palette, _layout, {
		"detail": str(options.get("detail", "block")),
		"mast_stock": Style.mast_stock(_style),
		"mast_foot": Style.mast_foot(_style),
	})
	add_child(_course)
	# After the build, because the ground is authored on the world layer and
	# only the environment axis separates the two. A no-op on `env=base`.
	if str(_style["env"]) != "base":
		var ground := _course.get_node_or_null("Terrain")
		if ground != null:
			Style.to_ground_layer(ground)
	_practicals()
	_collect_travellers()
	_report()

	_build_camera()
	set_time(0.0)
	if str(options.get("dump-physics", "")) != "":
		_dump_physics(str(options["dump-physics"]))
	if str(options.get("dump-style", "")) != "":
		_dump_style(str(options["dump-style"]))


func _options() -> Dictionary:
	var options := {}
	for argument in OS.get_cmdline_user_args():
		var arg: String = argument
		if not arg.begins_with("--"):
			continue
		var split := arg.substr(2).split("=", true, 1)
		if split.size() == 2:
			options[split[0]] = split[1]
	return options


func _report() -> void:
	var metrics: Dictionary = _course.get_meta("metrics")
	print("layout %s: %s" % [_layout, str(_table["title"])])
	print("  length %.1f  drop %.1f  span x %.1f z %.1f  grade %.1f deg" % [
		metrics["length"], metrics["drop"], metrics["span_x"],
		metrics["span_z"], metrics["mean_grade_deg"]])
	print("  start->finish %.1f  clearance %.2f..%.2f  buried piers %d" % [
		metrics["start_to_finish"], metrics["min_clearance"],
		metrics["max_clearance"], metrics["buried_piers"]])


func _practicals() -> void:
	## One warm or cool omni at each race moment, following the colour story.
	var nodes: Dictionary = _table["nodes"]
	var lamps := [
		["start", "#6BE9FF", 2.6, 9.0, 2.2],
		["mix", "#A379FF", 2.6, 8.0, 1.8],
		["obstacle", "#FF9A48", 3.0, 9.5, 2.4],
		["split", "#EAF7FF", 2.4, 9.0, 2.6],
		["merge", "#FFC168", 2.8, 9.0, 2.0],
		["finish", "#FFC46A", 3.4, 14.0, 2.6],
	]
	for entry in lamps:
		var name := str(entry[0])
		if not nodes.has(name):
			continue
		var lamp := OmniLight3D.new()
		lamp.name = "Lamp%s" % name.capitalize()
		lamp.position = (nodes[name] as Vector3) + Vector3(0.0,
			float(entry[4]), 0.0)
		lamp.light_color = Color(str(entry[1]))
		lamp.light_energy = float(entry[2])
		lamp.omni_range = float(entry[3])
		lamp.omni_attenuation = 1.5
		lamp.shadow_enabled = false
		add_child(lamp)


func _collect_travellers() -> void:
	var field := _course.get_node_or_null("Field")
	if field == null:
		return
	for entry in _course.get_meta("travellers"):
		var record: Dictionary = entry
		var node: Node3D = field.get_node_or_null(str(record["node"]))
		if node == null:
			continue
		var run := str(record["run"])
		_travellers.append({
			"node": node,
			"path": _course.get_meta("%s_path" % run),
			"banks": _course.get_meta("%s_banks" % run),
			"scale": float(_course.get_meta("%s_scale" % run)),
			"lane": float(record["lane"]),
			"phase": float(record["phase"]),
		})


# --- camera ---------------------------------------------------------------


func _aim_of(spec: Dictionary) -> Dictionary:
	## Resolve a shot's `at` clause to a world point and a forward direction.
	var at: Array = spec["at"]
	var kind := str(at[0])
	if kind == "hero":
		var hero: Dictionary = _table["hero"]
		var fitted := _hero_fit()
		return {"point": fitted["aim"], "forward": Vector3(0.0, 0.0, 1.0),
			"distance": float(fitted["distance"]), "fov": float(hero["fov"]),
			"elevation": float(hero["elevation"]),
			"azimuth": float(hero["azimuth"])}

	var point := Vector3.ZERO
	var forward := Vector3(0.0, 0.0, 1.0)
	if kind == "node":
		var nodes: Dictionary = _table["nodes"]
		point = nodes[str(at[1])]
		forward = _heading_near(point)
	else:
		var run := str(at[1]) if kind == "path" else _longest_run()
		var t: float = float(at[2]) if kind == "path" else float(at[1])
		var path: Array = _course.get_meta("%s_path" % run)
		point = _sample_at(path, t)
		forward = _heading_on(path, t)
	# Which way a bearing swings is decided by the ground, not by its sign.
	#
	# A side-on bearing of seventy-eight degrees is a tracking shot on one
	# layout and a camera buried in the mountain on the next, because "the
	# track's left" is uphill on a leg running one way and downhill on the leg
	# running back. So both candidates are tested against the terrain and the
	# one standing over lower ground wins. That is also the correct answer
	# artistically - the open side is the side with the view.
	var bearing: float = deg_to_rad(float(spec["bearing"]))
	var side := Vector3(forward.z, 0.0, -forward.x).normalized()
	var flat := Vector3(forward.x, 0.0, forward.z).normalized()
	var probe := 9.0
	var cfg: Dictionary = _table["terrain"]
	var left := point + side * probe
	var right := point - side * probe
	if Terrain.height(left.x, left.z, cfg) > Terrain.height(right.x, right.z, cfg):
		side = -side
	var direction := flat * cos(bearing) + side * sin(bearing)
	var fov: float = float(spec["fov"])
	var half := tan(deg_to_rad(fov) * 0.5)
	var distance: float = (float(spec["extent"]) * 0.5) / half
	return {"point": point, "forward": direction, "distance": distance,
		"fov": fov, "elevation": float(spec["elevation"]), "azimuth": NAN}


func _sample_at(path: Array, t: float) -> Vector3:
	var at: float = clampf(t, 0.0, 1.0) * float(path.size() - 1)
	var index: int = clampi(int(round(at)), 0, path.size() - 1)
	return path[index]


func _heading_on(path: Array, t: float) -> Vector3:
	var index: int = clampi(int(round(clampf(t, 0.0, 1.0)
		* float(path.size() - 1))), 1, path.size() - 2)
	var delta: Vector3 = (path[index + 1] as Vector3) - (path[index - 1] as Vector3)
	delta.y = 0.0
	if delta.length_squared() < 1.0e-8:
		return Vector3(0.0, 0.0, 1.0)
	return delta.normalized()


func _heading_near(point: Vector3) -> Vector3:
	## The direction of travel at the nearest sample of any run.
	var best := 1.0e9
	var heading := Vector3(0.0, 0.0, 1.0)
	for entry in _table["runs"]:
		var run := str((entry as Dictionary)["name"])
		var path: Array = _course.get_meta("%s_path" % run)
		for index in path.size():
			var distance: float = (path[index] as Vector3).distance_to(point)
			if distance < best:
				best = distance
				heading = _heading_on(path,
					float(index) / float(maxi(path.size() - 1, 1)))
	return heading


func _longest_run() -> String:
	var best := ""
	var longest := -1.0
	for entry in _table["runs"]:
		var spec: Dictionary = entry
		if str(spec["role"]) != "long":
			continue
		var path: Array = _course.get_meta("%s_path" % str(spec["name"]))
		var length: float = V2Forms.path_length(path)
		if length > longest:
			longest = length
			best = str(spec["name"])
	return best


## The establishing lens is solved, not typed.
##
## A course is a hundred and fifty units long and forty deep, so the distance
## that frames it depends on the *shape* of the layout as much as on its size -
## and three layouts with the same bounding box can need distances twenty per
## cent apart. Typing an extent per layout means every camera change is a
## re-measure, and the first study did exactly that and cropped all three.
##
## So the rig binary-searches the smallest distance at which every centreline
## sample and every module anchor falls inside the frame with `HERO_MARGIN` to
## spare, then shifts the aim to the middle of what it found and solves again.
## Two passes is enough; the second only ever moves it by a fraction.
const HERO_MARGIN := 0.09


func _course_points() -> Array:
	var points: Array = []
	for entry in _table["runs"]:
		var run := str((entry as Dictionary)["name"])
		points.append_array(_course.get_meta("%s_path" % run))
	for key in (_table["nodes"] as Dictionary):
		points.append((_table["nodes"] as Dictionary)[key])
	return points


func _aspect() -> float:
	var viewport := get_viewport()
	if viewport == null:
		return 0.5625
	var size := viewport.get_visible_rect().size
	if size.y <= 0.0:
		return 0.5625
	return size.x / size.y


func _direction(elevation: float, azimuth: float) -> Vector3:
	var e := deg_to_rad(elevation)
	var a := deg_to_rad(azimuth)
	return Vector3(sin(a) * cos(e), sin(e), cos(a) * cos(e))


func _fits(points: Array, camera_at: Vector3, target: Vector3,
		tan_h: float, tan_v: float) -> bool:
	var back := (camera_at - target).normalized()
	var right := Vector3.UP.cross(back)
	if right.length_squared() < 1.0e-8:
		right = Vector3.RIGHT
	right = right.normalized()
	var up := back.cross(right).normalized()
	for point in points:
		var v: Vector3 = (point as Vector3) - camera_at
		var depth := -v.dot(back)
		if depth < 0.5:
			return false
		if absf(v.dot(right)) > depth * tan_h:
			return false
		if absf(v.dot(up)) > depth * tan_v:
			return false
	return true


func _recentre(points: Array, camera_at: Vector3, target: Vector3) -> Vector3:
	var back := (camera_at - target).normalized()
	var right := Vector3.UP.cross(back).normalized()
	var up := back.cross(right).normalized()
	var lo := Vector2(1.0e9, 1.0e9)
	var hi := -lo
	for point in points:
		var v: Vector3 = (point as Vector3) - camera_at
		var depth := maxf(-v.dot(back), 0.5)
		var angular := Vector2(v.dot(right) / depth, v.dot(up) / depth)
		lo = Vector2(minf(lo.x, angular.x), minf(lo.y, angular.y))
		hi = Vector2(maxf(hi.x, angular.x), maxf(hi.y, angular.y))
	var mid := (lo + hi) * 0.5
	var reach := camera_at.distance_to(target)
	return target + right * mid.x * reach + up * mid.y * reach


func _hero_fit() -> Dictionary:
	if not _fitted.is_empty():
		return _fitted
	var hero: Dictionary = _table["hero"]
	var points := _course_points()
	var direction := _direction(float(hero["elevation"]),
		float(hero["azimuth"]))
	var tan_v := tan(deg_to_rad(float(hero["fov"])) * 0.5) * (1.0 - HERO_MARGIN)
	var tan_h := tan_v * _aspect()

	var target: Vector3 = hero["aim"]
	var distance := 100.0
	for _pass in 2:
		var lo := 6.0
		var hi := 3000.0
		for _step in 34:
			var mid := (lo + hi) * 0.5
			if _fits(points, target + direction * mid, target, tan_h, tan_v):
				hi = mid
			else:
				lo = mid
		distance = hi
		target = _recentre(points, target + direction * distance, target)
	_fitted = {"aim": target, "distance": distance}
	print("  hero lens: fov %.0f  elevation %.0f  azimuth %.0f  distance %.1f"
		% [float(hero["fov"]), float(hero["elevation"]),
			float(hero["azimuth"]), distance])
	return _fitted


func _build_camera() -> void:
	_camera = Camera3D.new()
	_camera.name = "CourseCamera"
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.near = 0.15
	_camera.far = 2400.0
	add_child(_camera)
	_camera.current = true
	_place_camera(0.0, 0.0)


func _place_camera(orbit_offset: float, dolly: float) -> void:
	var spec: Dictionary = SHOTS[_shot]
	var aim := _aim_of(spec)
	var fov: float = float(aim["fov"])
	var elevation := deg_to_rad(float(aim["elevation"]))
	var distance: float = float(aim["distance"]) * (1.0 + dolly)
	var target: Vector3 = aim["point"]

	var direction: Vector3
	if not is_nan(float(aim["azimuth"])):
		var azimuth := deg_to_rad(float(aim["azimuth"]) + orbit_offset)
		direction = Vector3(sin(azimuth) * cos(elevation), sin(elevation),
			cos(azimuth) * cos(elevation))
	else:
		var flat: Vector3 = aim["forward"]
		var spun := flat.rotated(Vector3.UP, deg_to_rad(orbit_offset))
		direction = (spun * cos(elevation) + Vector3.UP * sin(elevation))
		direction = direction.normalized()

	_camera.fov = fov
	_camera.position = target + direction * distance
	_camera.look_at(target, Vector3.UP)


func set_time(seconds: float) -> void:
	## Display motion only. Constant rate along each run; no physics implied.
	for entry in _travellers:
		var node: Node3D = entry["node"]
		var path: Array = entry["path"]
		var banks: Array = entry["banks"]
		var scale: float = float(entry["scale"])
		var t: float = fposmod(float(entry["phase"]) + seconds * 0.085, 1.0)
		var centre := Track.running_point(path, banks, t,
			Layout.MARBLE_RADIUS, scale)
		var index: int = clampi(int(round(t * float(path.size() - 1))), 0,
			path.size() - 1)
		var frame: Basis = V2Forms.banked_basis(path, banks, index)
		node.position = centre + frame.x * float(entry["lane"]) * scale

	if _sequenced:
		_place_sequence(seconds)
	else:
		_orbit = sin(seconds * 0.32) * 4.0
		_dolly = -0.03 * (1.0 - cos(seconds * 0.28))
		_place_camera(_orbit, _dolly)


func _place_sequence(seconds: float) -> void:
	## The camera for one instant of the cut list.
	var total := 0.0
	for entry in SEQUENCE:
		total += float((entry as Dictionary)["seconds"])
	var clock: float = fposmod(seconds, maxf(total, 0.001))
	var cursor := 0.0
	for entry in SEQUENCE:
		var cut: Dictionary = entry
		var length: float = float(cut["seconds"])
		if clock > cursor + length and cut != SEQUENCE[SEQUENCE.size() - 1]:
			cursor += length
			continue
		var t: float = clampf((clock - cursor) / maxf(length, 0.001), 0.0, 1.0)
		# Eased across the cut, so a move settles rather than stopping dead.
		var eased := smoothstep(0.0, 1.0, t)
		if cut.has("follow"):
			var span: Array = cut["t"]
			_shot = "_follow"
			SHOTS["_follow"] = {
				"at": ["path", str(cut["follow"]),
					lerpf(float(span[0]), float(span[1]), eased)],
				"extent": float(cut["extent"]), "fov": float(cut["fov"]),
				"elevation": float(cut["elevation"]),
				"bearing": float(cut["bearing"]),
			}
			_place_camera(0.0, 0.0)
			return
		var orbit: Array = cut["orbit"]
		var dolly: Array = cut["dolly"]
		_shot = str(cut["shot"])
		_place_camera(lerpf(float(orbit[0]), float(orbit[1]), eased),
			lerpf(float(dolly[0]), float(dolly[1]), eased))
		return


# --- physics metadata -----------------------------------------------------


func _dump_style(path: String) -> void:
	## The resolved palette, as a document.
	##
	## Written from the live palette after the whole machine has been built,
	## so every value in it is a value that was actually rendered. A swatch
	## sheet drawn from hexes retyped into a Python table is a drawing of the
	## table, not of the frame.
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("course_scene: cannot write %s" % path)
		return
	file.store_string(JSON.stringify(Style.dump(_palette, _style), "  "))
	file.close()
	print("style dump -> %s" % path)


func _dump_physics(path: String) -> void:
	## Everything a PyBullet pass would need, and nothing it would not.
	##
	## Written from the *built* scene rather than from the layout table, so it
	## records the geometry that was actually photographed - the resampled
	## centrelines, the solved bank angles, the module yaws the placer worked
	## out - and cannot drift from it. Read it as a description of a shape, not
	## as a set of colliders: no collider in this branch exists.
	var metrics: Dictionary = _course.get_meta("metrics")
	var terrain: Dictionary = (_table["terrain"] as Dictionary).duplicate()
	terrain.erase("cut_index")

	var runs: Array = []
	for entry in _table["runs"]:
		var spec: Dictionary = entry
		var name := str(spec["name"])
		var path_points: Array = _course.get_meta("%s_path" % name)
		var banks: Array = _course.get_meta("%s_banks" % name)
		var scale: float = float(_course.get_meta("%s_scale" % name))
		runs.append({
			"name": name,
			"role": str(spec["role"]),
			"profile_scale": scale,
			"clear_width": Track.clear_width() * scale,
			"floor_offset": Track.floor_offset() * scale,
			"origin": path_points[0],
			"entry_socket": {"at": path_points[0],
				"heading_deg": rad_to_deg(_heading_on(path_points, 0.0).angle_to(
					Vector3(0.0, 0.0, 1.0)))},
			"exit_socket": {"at": path_points[path_points.size() - 1],
				"heading_deg": rad_to_deg(_heading_on(path_points,
					1.0).angle_to(Vector3(0.0, 0.0, 1.0)))},
			"length": V2Forms.path_length(path_points),
			"drop": float((path_points[0] as Vector3).y)
				- float((path_points[path_points.size() - 1] as Vector3).y),
			"slope_deg": _slope_profile(path_points),
			"bank_max_deg": _bank_extreme(banks),
			"bounds": _bounds(path_points, 1.13 * scale, 0.98 * scale, 0.32),
			"centreline": _thinned(path_points, 26),
		})

	var modules: Array = []
	var nodes: Dictionary = _table["nodes"]
	var course_modules := _course.get_node_or_null("Modules")
	if course_modules != null:
		for child in course_modules.get_children():
			var node: Node3D = child
			var key := node.name.to_lower()
			modules.append({
				"name": node.name,
				"origin": node.position,
				"yaw_deg": rad_to_deg(node.rotation.y),
				"anchor": nodes.get(key, node.position),
				"action_clearance": _module_clearance(node.name),
			})

	var cameras: Array = []
	var was := _shot
	for name in SHOTS.keys():
		if str(name).begins_with("_"):
			continue
		_shot = str(name)
		_place_camera(0.0, 0.0)
		cameras.append({
			"name": str(name),
			"position": _camera.position,
			"aim": _aim_of(SHOTS[name])["point"],
			"fov": _camera.fov,
		})
	_shot = was
	_place_camera(0.0, 0.0)

	var table := {
		"branch": "marble-sloped-course-lab",
		"layout": _layout,
		"title": str(_table["title"]),
		"fairness": "UNVERIFIED. Nothing in this branch simulates. The start"
			+ " grid, the mixer pin rows and the two branch lengths are"
			+ " shapes, not proofs, and no lane-bias claim may be made from"
			+ " them until a PyBullet pass measures one.",
		"physics": "NOT ATTACHED. No collider, no solver, no seed. Every"
			+ " number here describes photographed geometry.",
		"marble": {"radius": Layout.MARBLE_RADIUS,
			"diameter": Layout.MARBLE_RADIUS * 2.0},
		"course": metrics,
		"terrain": terrain,
		"runs": runs,
		"modules": modules,
		"cameras": cameras,
	}
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("course_scene: cannot write %s" % path)
		return
	file.store_string(JSON.stringify(_jsonable(table), "  "))
	file.close()
	print("  physics -> %s" % path)


func _slope_profile(path: Array) -> Dictionary:
	## Gradient over the first, middle and last third of a run.
	var out := {}
	var names := ["entry", "middle", "exit"]
	for third in 3:
		var a: int = int(float(third) * float(path.size() - 1) / 3.0)
		var b: int = int(float(third + 1) * float(path.size() - 1) / 3.0)
		var run := 0.0
		for index in range(a, b):
			run += Vector2((path[index + 1] as Vector3).x
				- (path[index] as Vector3).x,
				(path[index + 1] as Vector3).z
				- (path[index] as Vector3).z).length()
		var fall: float = float((path[a] as Vector3).y) 			- float((path[b] as Vector3).y)
		out[names[third]] = rad_to_deg(atan(fall / maxf(run, 0.001)))
	return out


func _bank_extreme(banks: Array) -> float:
	var most := 0.0
	for value in banks:
		most = maxf(most, absf(float(value)))
	return rad_to_deg(most)


func _bounds(path: Array, half: float, below: float, above: float) -> Dictionary:
	var lo := Vector3(1.0e9, 1.0e9, 1.0e9)
	var hi := -lo
	for point in path:
		var p: Vector3 = point
		lo = Vector3(minf(lo.x, p.x - half), minf(lo.y, p.y - below),
			minf(lo.z, p.z - half))
		hi = Vector3(maxf(hi.x, p.x + half), maxf(hi.y, p.y + above),
			maxf(hi.z, p.z + half))
	return {"min": lo, "max": hi}


func _thinned(path: Array, count: int) -> Array:
	var out: Array = []
	for step in count:
		var index: int = clampi(int(round(float(step)
			* float(path.size() - 1) / float(count - 1))), 0, path.size() - 1)
		out.append(path[index])
	return out


func _module_clearance(name: String) -> Dictionary:
	## The volume each module needs kept free above the running surface.
	match name:
		"Start":
			return {"above": 1.10, "lateral": 3.30,
				"note": "eight bays at 0.63 pitch, gate bar at +0.26"}
		"Mixer":
			return {"above": 0.90, "lateral": 1.60,
				"note": "two staggered pin rows behind the window"}
		"Obstacle":
			return {"above": 1.70, "lateral": 1.80,
				"note": "three spinners, hub at +1.46, blade tips reach -0.05"}
		"Split":
			return {"above": 2.60, "lateral": 3.60,
				"note": "wedge nose on the centreline, portals at +/-2.05"}
		"Merge":
			return {"above": 1.20, "lateral": 2.60,
				"note": "two inlets at +/-1.10, one exit"}
		"Finish":
			return {"above": 4.20, "lateral": 6.30,
				"note": "deck 12.6 by 9.8, eight catch lanes at 1.32 pitch"}
	return {"above": 1.0, "lateral": 2.0, "note": ""}


func _jsonable(value):
	if value is Dictionary:
		var out := {}
		for key in value:
			out[str(key)] = _jsonable(value[key])
		return out
	if value is Array:
		var list: Array = []
		for item in value:
			list.append(_jsonable(item))
		return list
	if value is Vector3:
		return [snappedf(value.x, 0.001), snappedf(value.y, 0.001),
			snappedf(value.z, 0.001)]
	if value is float:
		return snappedf(value, 0.0001)
	return value


func shot_names() -> Array:
	return SHOTS.keys()


func set_shot(name: String) -> void:
	if SHOTS.has(name):
		_shot = name
		_place_camera(_orbit, _dolly)
