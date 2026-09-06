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

# at: ["node", name] or ["path", run, t]. `bearing` is measured from the
# track's own forward direction at the aim point - 0 looks up the course from
# in front of it, 90 is a side tracking position, 180 follows from behind.
const SHOTS := {
	"hero": {"at": ["hero"], "extent": 0.0, "fov": 0.0, "elevation": 0.0,
		"bearing": 0.0},
	"phone": {"at": ["hero"], "extent": 0.0, "fov": 0.0, "elevation": 0.0,
		"bearing": 0.0},
	"start": {"at": ["node", "start"], "extent": 11.0, "fov": 34.0,
		"elevation": 13.0, "bearing": 152.0},
	"descent": {"at": ["path", "launch", 0.72], "extent": 15.0, "fov": 36.0,
		"elevation": 11.0, "bearing": 134.0},
	"long_track": {"at": ["long", 0.46], "extent": 22.0, "fov": 34.0,
		"elevation": 9.0, "bearing": 74.0},
	"obstacle": {"at": ["node", "obstacle"], "extent": 12.0, "fov": 34.0,
		"elevation": 15.0, "bearing": 118.0},
	"split": {"at": ["node", "split"], "extent": 26.0, "fov": 34.0,
		"elevation": 26.0, "bearing": 168.0},
	"final_run": {"at": ["path", "final", 0.30], "extent": 17.0, "fov": 36.0,
		"elevation": 8.0, "bearing": 158.0},
	"finish": {"at": ["node", "finish"], "extent": 13.0, "fov": 34.0,
		"elevation": 12.0, "bearing": 24.0},
}

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


func _ready() -> void:
	var options := _options()
	_layout = str(options.get("layout", "a"))
	_shot = str(options.get("shot", DEFAULT_SHOT))
	_no_glow = str(options.get("no-glow", "")) != ""
	if not SHOTS.has(_shot):
		push_error("course_scene: unknown shot '%s'" % _shot)
		_shot = DEFAULT_SHOT

	_palette = Palette.new("tower")
	_table = Layout.table(_layout)

	var world_env := WorldEnvironment.new()
	world_env.name = "WorldEnvironment"
	world_env.environment = World.build_environment(_no_glow)
	add_child(world_env)

	World.build_lights(self)
	add_child(World.build(_palette))

	_course = Machine.build(_palette, _layout, {
		"detail": str(options.get("detail", "block")),
	})
	add_child(_course)
	_practicals()
	_collect_travellers()
	_report()

	_build_camera()
	set_time(0.0)


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
	var bearing: float = deg_to_rad(float(spec["bearing"]))
	var side := Vector3(forward.z, 0.0, -forward.x).normalized()
	var flat := Vector3(forward.x, 0.0, forward.z).normalized()
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

	_orbit = sin(seconds * 0.32) * 4.0
	_dolly = -0.03 * (1.0 - cos(seconds * 0.28))
	_place_camera(_orbit, _dolly)


func shot_names() -> Array:
	return SHOTS.keys()


func set_shot(name: String) -> void:
	if SHOTS.has(name):
		_shot = name
		_place_camera(_orbit, _dolly)
