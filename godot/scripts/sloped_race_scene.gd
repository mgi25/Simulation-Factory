extends "res://scripts/course_scene.gd"

## THE REAL RACE, on the approved sloped course.
##
## Extends the layout proof's scene rather than replacing it, so the course in
## frame is the course that was photographed: the same terrain, the same
## channel, the same seven modules, the same two-key lighting and the same
## practicals. Three things change, and they are the whole of this file.
##
## **The display marbles go.** `course_scene.gd` animates eight spheres along
## the centrelines at a constant rate to show that the course is a route. That
## is exactly what section 32 forbids here: the marbles in this render are the
## replay's, or there are none.
##
## **The marbles come from a replay.** PyBullet is authoritative and nothing in
## this file steps a simulation. `set_time` reads two frames of the replay,
## interpolates between them, and writes eight transforms.
##
## **The camera comes from a track.** `sloped.cameras` solves the whole
## sequence in Python - a position, an aim and a field of view per frame per cut
## - and this reads it. The camera in a race has to know where the pack is, and
## the pack's position is a fact about the replay rather than about the scene.
##
## ## The one scale in the pipeline
##
## The replay is in simulation units, where a marble's radius is 0.5. The course
## is authored in layout units, where it is 0.285. `sloped.scale` explains why
## the physics runs at the larger scale; what matters here is that the
## conversion happens **once**, as a uniform scale on the node the marbles are
## parented to. A uniform scale on a parent scales its children's translations
## and their radii together, so one number puts an 0.5-unit marble at the right
## size *and* the right place. Forget it and the marbles are 1.75 times too big
## and in the wrong place, which is not a subtle failure.
##
## The factor is read from the replay's own `units.render_scale` rather than
## hard-coded, so a replay and a scene cannot disagree about it.
##
## Usage, after `--`:
##
##     --replay=PATH        the marble3d replay JSON  (required)
##     --cameras=PATH       the camera track JSON     (required for a clip)
##     --layout=b --detail=hero
##     --shot=NAME          override with a still lens from SHOTS

const Palette := preload("res://assets/marble_machine/lab_palette.gd")

var _replay: Dictionary = {}
var _camera_track: Dictionary = {}
var _marble_root: Node3D
var _marbles: Array[Node3D] = []
var _wheels: Array = []
var _frame_times: PackedFloat32Array = PackedFloat32Array()
var _replay_fps := 60.0
var _render_scale := 0.57
var _duration := 0.0
var _use_track := false


func _ready() -> void:
	super()
	_strip_display_field()
	var options := _options()
	if str(options.get("replay", "")) != "":
		_load_replay(str(options["replay"]))
	if str(options.get("cameras", "")) != "":
		_load_cameras(str(options["cameras"]))
	_collect_wheels()
	set_time(0.0)


func _strip_display_field() -> void:
	## The layout proof's eight travelling spheres, removed rather than hidden.
	##
	## Hidden would be enough for the render and not enough for the claim: a
	## hidden node is one `visible = true` away from being in a frame beside the
	## real field, and "these are the physics marbles" has to be true of the
	## scene and not only of this run.
	_travellers.clear()
	if _course == null:
		return
	var field := _course.get_node_or_null("Field")
	if field != null:
		field.get_parent().remove_child(field)
		field.queue_free()


# --- the replay -----------------------------------------------------------


func _load_replay(path: String) -> void:
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		push_error("sloped_race_scene: cannot read replay %s" % path)
		return
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("sloped_race_scene: %s is not a replay object" % path)
		return
	_replay = parsed
	if str(_replay.get("mode", "marble3d")) != "marble3d":
		push_error("sloped_race_scene: %s is not a marble3d replay" % path)

	var units: Dictionary = _replay.get("units", {})
	if units.has("render_scale"):
		_render_scale = float(units["render_scale"])
	else:
		push_error("sloped_race_scene: replay carries no units.render_scale")
	_replay_fps = maxf(1.0, float(_replay.get("replay_fps", 60)))

	var frames: Array = _replay.get("frames", [])
	_frame_times.resize(frames.size())
	for index in frames.size():
		_frame_times[index] = float((frames[index] as Dictionary)["t"])
	_duration = 0.0 if frames.is_empty() else _frame_times[frames.size() - 1]

	_marble_root = Node3D.new()
	_marble_root.name = "Racers"
	# The one conversion. See the class docstring.
	_marble_root.scale = Vector3.ONE * _render_scale
	add_child(_marble_root)

	var info: Array = _replay.get("marbles", [])
	for index in info.size():
		var record: Dictionary = info[index]
		var radius := float(record.get("radius", 0.5))
		var sphere := SphereMesh.new()
		sphere.radius = radius
		sphere.height = radius * 2.0
		sphere.radial_segments = 32
		sphere.rings = 16
		var node := MeshInstance3D.new()
		node.name = "Racer%d" % int(record.get("id", index))
		node.mesh = sphere
		node.material_override = _palette.marble(int(record.get("id", index)))
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		_marble_root.add_child(node)
		_marbles.append(node)

	print("replay: seed %d, %d marbles, %d frames, %.2f s, render scale %.4f" % [
		int(_replay.get("seed", -1)), _marbles.size(), frames.size(), _duration,
		_render_scale])


func _load_cameras(path: String) -> void:
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		push_error("sloped_race_scene: cannot read camera track %s" % path)
		return
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("sloped_race_scene: %s is not a camera track" % path)
		return
	_camera_track = parsed
	_use_track = true
	var cuts: Array = _camera_track.get("cuts", [])
	var names: PackedStringArray = PackedStringArray()
	for cut in cuts:
		names.append("%s %.2f-%.2f" % [str((cut as Dictionary)["name"]),
			float((cut as Dictionary)["from"]), float((cut as Dictionary)["to"])])
	print("cameras: %d cuts  %s" % [cuts.size(), ", ".join(names)])


func _collect_wheels() -> void:
	## The obstacle's three visual paddle wheels, so the replay can turn them.
	if _course == null:
		return
	var modules := _course.get_node_or_null("Modules")
	if modules == null:
		return
	var obstacle := modules.get_node_or_null("Obstacle")
	if obstacle == null:
		return
	for index in 3:
		var spinner := obstacle.get_node_or_null("Spinner%d" % index)
		if spinner == null:
			continue
		var wheel := spinner.get_node_or_null("Wheel")
		if wheel != null:
			_wheels.append({"wheel": wheel, "index": index})


# --- playback -------------------------------------------------------------


func _frame_pair(seconds: float) -> Array:
	## The two replay frames either side of `seconds`, and the blend between.
	##
	## The physics rate is a whole multiple of the replay rate, so a replay
	## frame is an exact tick rather than a blend of two - but the *output* rate
	## need not equal the replay rate, and a render at 60 fps of a replay at 60
	## fps lands on frames exactly while a still at an arbitrary second does
	## not. So the pair is found by index and interpolated, and at 60 fps the
	## blend is zero and nothing is interpolated at all.
	var count := _frame_times.size()
	if count == 0:
		return [0, 0, 0.0]
	var at: float = clampf(seconds, 0.0, _duration) * _replay_fps
	var low: int = clampi(int(floor(at)), 0, count - 1)
	var high: int = clampi(low + 1, 0, count - 1)
	var span: float = _frame_times[high] - _frame_times[low]
	var blend := 0.0
	if span > 1.0e-9:
		blend = clampf((clampf(seconds, 0.0, _duration) - _frame_times[low]) / span,
			0.0, 1.0)
	return [low, high, blend]


func set_time(seconds: float) -> void:
	if _replay.is_empty():
		super(seconds)
		return

	var frames: Array = _replay["frames"]
	var pair := _frame_pair(seconds)
	var low: Dictionary = frames[int(pair[0])]
	var high: Dictionary = frames[int(pair[1])]
	var blend: float = float(pair[2])

	var low_marbles: Array = low["marbles"]
	var high_marbles: Array = high["marbles"]
	for index in _marbles.size():
		if index >= low_marbles.size():
			break
		var a: Dictionary = low_marbles[index]
		var b: Dictionary = high_marbles[index] if index < high_marbles.size() else a
		var node: Node3D = _marbles[index]
		node.position = _vec(a["p"]).lerp(_vec(b["p"]), blend)
		node.quaternion = _quat(a["q"]).slerp(_quat(b["q"]), blend)

	_turn_wheels(low, high, blend)

	if _use_track:
		_place_from_track(seconds)
	else:
		_place_camera(0.0, 0.0)


func _vec(raw) -> Vector3:
	var values: Array = raw
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


func _quat(raw) -> Quaternion:
	var values: Array = raw
	return Quaternion(float(values[0]), float(values[1]), float(values[2]),
		float(values[3])).normalized()


func _turn_wheels(low: Dictionary, high: Dictionary, blend: float) -> void:
	## The visual paddle wheels, turned to where the replay's blades are.
	##
	## Taken from the blade's own recorded pose rather than recomputed from the
	## spinner's phase and rate, so the drawn blade and the colliding blade
	## cannot drift apart. The angle is the blade's offset from its hub,
	## projected into the wheel's parent frame - which is exact, and does not
	## depend on either side agreeing about a sign convention.
	var actuators: Dictionary = low.get("a", {})
	var next_actuators: Dictionary = high.get("a", {})
	for entry in _wheels:
		var record: Dictionary = entry
		var key := "obstacle.wheel%d_blade0" % int(record["index"])
		if not actuators.has(key):
			continue
		var pose: Array = actuators[key]
		var position := _vec(pose[0]) * _render_scale
		if next_actuators.has(key):
			var later: Array = next_actuators[key]
			position = position.lerp(_vec(later[0]) * _render_scale, blend)
		var wheel: Node3D = record["wheel"]
		var parent := wheel.get_parent() as Node3D
		if parent == null:
			continue
		var local := parent.global_transform.affine_inverse() * position
		wheel.rotation.y = atan2(local.x, local.z)


func _place_from_track(seconds: float) -> void:
	## The camera for one instant of the solved sequence.
	var cuts: Array = _camera_track.get("cuts", [])
	if cuts.is_empty():
		return
	var chosen: Dictionary = cuts[cuts.size() - 1]
	for cut in cuts:
		var record: Dictionary = cut
		if seconds <= float(record["to"]):
			chosen = record
			break
	var rows: Array = chosen["frames"]
	if rows.is_empty():
		return
	# The row nearest in time, then a linear blend to the next. The track is
	# sampled at the replay rate, so at 60 fps this lands on a row exactly.
	var first := float((rows[0] as Array)[0])
	var at: float = (clampf(seconds, first, float((rows[rows.size() - 1] as Array)[0]))
		- first) * float(_camera_track.get("fps", 60))
	var low: int = clampi(int(floor(at)), 0, rows.size() - 1)
	var high: int = clampi(low + 1, 0, rows.size() - 1)
	var a: Array = rows[low]
	var b: Array = rows[high]
	var blend: float = clampf(at - float(low), 0.0, 1.0)

	var position := Vector3(float(a[1]), float(a[2]), float(a[3])).lerp(
		Vector3(float(b[1]), float(b[2]), float(b[3])), blend)
	var aim := Vector3(float(a[4]), float(a[5]), float(a[6])).lerp(
		Vector3(float(b[4]), float(b[5]), float(b[6])), blend)
	_camera.fov = lerpf(float(a[7]), float(b[7]), blend)
	_camera.position = position
	if position.distance_to(aim) > 1.0e-4:
		_camera.look_at(aim, Vector3.UP)


func replay_duration() -> float:
	return _duration


func cut_names() -> PackedStringArray:
	var out := PackedStringArray()
	for cut in _camera_track.get("cuts", []):
		out.append(str((cut as Dictionary)["name"]))
	return out


func cut_midpoint(name: String) -> float:
	for cut in _camera_track.get("cuts", []):
		var record: Dictionary = cut
		if str(record["name"]) == name:
			return 0.5 * (float(record["from"]) + float(record["to"]))
	return 0.0
