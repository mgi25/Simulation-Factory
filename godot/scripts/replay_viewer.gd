extends Node3D

## Plays back a replay exported by the Python simulation.
##
## Godot is presentation only: it runs no physics and no game rules. Every
## position, health value and result comes from the replay file. The scene
## (arena, walls, spheres, camera, lights, HUD) is built from replay data so
## nothing here duplicates the simulation's numbers.

# The single place where logical simulation pixels become Godot world units.
const PIXELS_PER_UNIT := 100.0

const DEFAULT_REPLAY := "../output/replay_12345.json"

const FLOOR_THICKNESS := 0.25
const WALL_HEIGHT := 0.9
const WALL_THICKNESS := 0.16

const CAMERA_FOV := 50.0
const CAMERA_ELEVATION_DEG := 68.0
const CAMERA_MARGIN := 0.7

const HUD_WIDTH := 1080.0
const HEALTH_BAR_POSITION := Vector2(300.0, 0.0)
const HEALTH_BAR_SIZE := Vector2(500.0, 34.0)
const HEALTH_ROW_Y := [160.0, 250.0]

var _replay: Dictionary = {}
var _frames: Array = []
var _fighter_meta: Array = []
var _fps := 60.0

var _arena_center := Vector2.ZERO
var _arena_units := Vector2.ONE

var _spheres: Array[MeshInstance3D] = []
var _live_materials: Array[StandardMaterial3D] = []
var _dead_materials: Array[StandardMaterial3D] = []

var _timer_label: Label
var _result_label: Label
var _health_labels: Array[Label] = []
var _health_fills: Array[ColorRect] = []

var _playhead := 0.0


func _ready() -> void:
	var path := _resolve_path(_replay_path_argument())
	if not _load_replay(path):
		_build_hud_root_error(path)
		return

	_read_arena()
	_build_environment()
	_build_lights()
	_build_camera()
	_build_arena()
	_build_fighters()
	_build_hud()
	_apply_playhead(0.0)

	print("replay loaded: seed=%s frames=%d duration=%.2fs" % [
		str(_replay.get("seed", "?")),
		_frames.size(),
		float(_replay.get("result", {}).get("duration", 0.0)),
	])


func _process(delta: float) -> void:
	if _frames.size() < 2:
		return
	var last := float(_frames.size() - 1)
	_apply_playhead(minf(_playhead + delta * _fps, last))


# --- coordinate conversion -----------------------------------------------

func to_world(sim_x: float, sim_y: float, height: float) -> Vector3:
	## Simulation x maps to world X, simulation y to world Z, Y is visual only.
	return Vector3(
		(sim_x - _arena_center.x) / PIXELS_PER_UNIT,
		height,
		(sim_y - _arena_center.y) / PIXELS_PER_UNIT)


func to_units(pixels: float) -> float:
	return pixels / PIXELS_PER_UNIT


# --- replay loading ------------------------------------------------------

func _replay_path_argument() -> String:
	var args := OS.get_cmdline_user_args()
	for i in args.size():
		var arg: String = args[i]
		if arg.begins_with("--replay="):
			return arg.substr(9)
		if arg == "--replay" and i + 1 < args.size():
			return args[i + 1]
	return DEFAULT_REPLAY


func _resolve_path(path: String) -> String:
	## Relative paths are resolved against the Godot project directory.
	if path.begins_with("res://") or path.begins_with("user://"):
		return path
	if path.is_absolute_path():
		return path
	return ProjectSettings.globalize_path("res://").path_join(path).simplify_path()


func _load_replay(path: String) -> bool:
	if not FileAccess.file_exists(path):
		push_error("Replay file not found: %s" % path)
		return false

	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("Replay file is not a JSON object: %s" % path)
		return false

	var data: Dictionary = parsed
	if int(data.get("version", 0)) != 1:
		push_error("Unsupported replay version: %s" % str(data.get("version")))
		return false

	var frames: Array = data.get("frames", [])
	var fighters: Array = data.get("fighters", [])
	if frames.is_empty() or fighters.is_empty():
		push_error("Replay contains no frames or no fighters: %s" % path)
		return false

	_replay = data
	_frames = frames
	_fighter_meta = fighters
	_fps = float(data.get("fps", 60.0))
	return true


func _read_arena() -> void:
	var arena: Dictionary = _replay.get("arena", {})
	var left := float(arena.get("left", 0.0))
	var top := float(arena.get("top", 0.0))
	var right := float(arena.get("right", 0.0))
	var bottom := float(arena.get("bottom", 0.0))
	_arena_center = Vector2((left + right) * 0.5, (top + bottom) * 0.5)
	_arena_units = Vector2(right - left, bottom - top) / PIXELS_PER_UNIT


# --- scene construction --------------------------------------------------

func _build_environment() -> void:
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.09, 0.11, 0.19)
	sky_material.sky_horizon_color = Color(0.19, 0.21, 0.29)
	sky_material.ground_horizon_color = Color(0.10, 0.11, 0.16)
	sky_material.ground_bottom_color = Color(0.04, 0.04, 0.07)

	var sky := Sky.new()
	sky.sky_material = sky_material

	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_sky_contribution = 1.0
	environment.ambient_light_energy = 1.0
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	# Restrained glow: highlights pop without washing the arena out.
	environment.glow_enabled = true
	environment.glow_intensity = 0.25
	environment.glow_bloom = 0.05
	environment.glow_hdr_threshold = 1.1

	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	world.environment = environment
	add_child(world)


func _build_lights() -> void:
	var key := DirectionalLight3D.new()
	key.name = "KeyLight"
	key.light_color = Color(1.0, 0.97, 0.92)
	key.light_energy = 1.7
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	key.directional_shadow_max_distance = 60.0
	key.shadow_bias = 0.04
	key.rotation_degrees = Vector3(-52.0, 38.0, 0.0)
	add_child(key)

	var fill := DirectionalLight3D.new()
	fill.name = "FillLight"
	fill.light_color = Color(0.70, 0.79, 1.0)
	fill.light_energy = 0.45
	fill.shadow_enabled = false
	fill.rotation_degrees = Vector3(-24.0, -140.0, 0.0)
	add_child(fill)


func _build_camera() -> void:
	var camera := Camera3D.new()
	camera.name = "Camera3D"
	camera.fov = CAMERA_FOV
	camera.near = 0.1
	camera.far = 300.0

	# Vertical 9:16 framing: the horizontal field of view is the tight one,
	# so the distance has to satisfy both the arena width and its depth.
	var viewport_width := float(ProjectSettings.get_setting(
		"display/window/size/viewport_width", 1080))
	var viewport_height := float(ProjectSettings.get_setting(
		"display/window/size/viewport_height", 1920))
	var half_v := deg_to_rad(CAMERA_FOV * 0.5)
	var half_h := atan(tan(half_v) * viewport_width / viewport_height)
	var elevation := deg_to_rad(CAMERA_ELEVATION_DEG)

	var fit_width := (_arena_units.x * 0.5 + CAMERA_MARGIN) / tan(half_h)
	var fit_depth := (_arena_units.y * 0.5 * sin(elevation) + CAMERA_MARGIN) / tan(half_v)
	var distance := maxf(fit_width, fit_depth)

	camera.position = Vector3(0.0, distance * sin(elevation), distance * cos(elevation))
	add_child(camera)
	camera.look_at(Vector3.ZERO, Vector3.UP)


func _build_arena() -> void:
	var half := _arena_units * 0.5
	var outer_x := _arena_units.x + WALL_THICKNESS * 2.0
	var outer_z := _arena_units.y + WALL_THICKNESS * 2.0

	var floor_mesh := BoxMesh.new()
	floor_mesh.size = Vector3(outer_x, FLOOR_THICKNESS, outer_z)
	var floor_node := MeshInstance3D.new()
	floor_node.name = "Floor"
	floor_node.mesh = floor_mesh
	floor_node.material_override = _make_material(Color(0.13, 0.14, 0.19), 0.15, 0.55)
	floor_node.position = Vector3(0.0, -FLOOR_THICKNESS * 0.5, 0.0)
	add_child(floor_node)

	# Wall inner faces sit exactly on the arena bounds, like the Pymunk walls.
	var wall_material := _make_material(Color(0.30, 0.33, 0.42), 0.55, 0.35)
	var side_size := Vector3(WALL_THICKNESS, WALL_HEIGHT, outer_z)
	var end_size := Vector3(outer_x, WALL_HEIGHT, WALL_THICKNESS)
	var wall_y := WALL_HEIGHT * 0.5
	var wall_x := half.x + WALL_THICKNESS * 0.5
	var wall_z := half.y + WALL_THICKNESS * 0.5

	var walls := [
		["WallLeft", side_size, Vector3(-wall_x, wall_y, 0.0)],
		["WallRight", side_size, Vector3(wall_x, wall_y, 0.0)],
		["WallTop", end_size, Vector3(0.0, wall_y, -wall_z)],
		["WallBottom", end_size, Vector3(0.0, wall_y, wall_z)],
	]
	for wall in walls:
		var mesh := BoxMesh.new()
		mesh.size = wall[1]
		var node := MeshInstance3D.new()
		node.name = wall[0]
		node.mesh = mesh
		node.material_override = wall_material
		node.position = wall[2]
		add_child(node)


func _build_fighters() -> void:
	for meta in _fighter_meta:
		var radius := to_units(float(meta.get("radius", 40.0)))
		var color := _color_of(meta)

		var mesh := SphereMesh.new()
		mesh.radius = radius
		mesh.height = radius * 2.0
		mesh.radial_segments = 48
		mesh.rings = 24

		var live := _make_material(color, 0.45, 0.24)
		var dead := _make_material(color.darkened(0.72), 0.15, 0.7)

		var node := MeshInstance3D.new()
		node.name = "Fighter%s" % str(meta.get("id", 0))
		node.mesh = mesh
		node.material_override = live
		node.position = to_world(_arena_center.x, _arena_center.y, radius)
		add_child(node)

		_spheres.append(node)
		_live_materials.append(live)
		_dead_materials.append(dead)


func _make_material(color: Color, metallic: float, roughness: float) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = metallic
	material.metallic_specular = 0.6
	material.roughness = roughness
	return material


func _color_of(meta: Dictionary) -> Color:
	var raw: Variant = meta.get("color", [])
	if raw is Array and (raw as Array).size() >= 3:
		var rgb: Array = raw
		return Color8(int(rgb[0]), int(rgb[1]), int(rgb[2]))
	return Color.WHITE


# --- HUD -----------------------------------------------------------------

func _build_hud_root() -> Control:
	var layer := CanvasLayer.new()
	layer.name = "HUD"
	add_child(layer)

	var root := Control.new()
	root.name = "HudRoot"
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(root)
	return root


func _build_hud_root_error(path: String) -> void:
	var root := _build_hud_root()
	_make_label(root, "No replay at\n%s" % path, 40, Color(1.0, 0.5, 0.5),
		Rect2(40.0, 800.0, HUD_WIDTH - 80.0, 320.0), HORIZONTAL_ALIGNMENT_CENTER)


func _build_hud() -> void:
	var root := _build_hud_root()

	_timer_label = _make_label(root, "0.0", 76, Color(0.91, 0.92, 0.94),
		Rect2(0.0, 30.0, HUD_WIDTH, 84.0), HORIZONTAL_ALIGNMENT_CENTER)

	for i in _fighter_meta.size():
		var meta: Dictionary = _fighter_meta[i]
		var row_y := float(HEALTH_ROW_Y[i]) if i < HEALTH_ROW_Y.size() else 160.0 + 90.0 * i
		var color := _color_of(meta)

		_make_label(root, str(meta.get("name", "?")), 44, color,
			Rect2(60.0, row_y, 220.0, 60.0), HORIZONTAL_ALIGNMENT_LEFT)

		var track := ColorRect.new()
		track.color = Color(0.16, 0.17, 0.22, 0.92)
		track.position = Vector2(HEALTH_BAR_POSITION.x, row_y + (60.0 - HEALTH_BAR_SIZE.y) * 0.5)
		track.size = HEALTH_BAR_SIZE
		root.add_child(track)

		var fill := ColorRect.new()
		fill.color = color
		fill.position = track.position
		fill.size = HEALTH_BAR_SIZE
		root.add_child(fill)
		_health_fills.append(fill)

		_health_labels.append(_make_label(root, "", 44, Color(0.91, 0.92, 0.94),
			Rect2(820.0, row_y, 200.0, 60.0), HORIZONTAL_ALIGNMENT_RIGHT))

	_result_label = _make_label(root, _result_text(), 92, Color(0.96, 0.97, 1.0),
		Rect2(0.0, 1620.0, HUD_WIDTH, 120.0), HORIZONTAL_ALIGNMENT_CENTER)
	_result_label.visible = false


func _make_label(parent: Control, text: String, font_size: int, color: Color,
		rect: Rect2, alignment: int) -> Label:
	var label := Label.new()
	label.text = text
	label.position = rect.position
	label.size = rect.size
	label.horizontal_alignment = alignment
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	# Built-in Godot font only - no external font assets.
	var settings := LabelSettings.new()
	settings.font_size = font_size
	settings.font_color = color
	settings.outline_size = 6
	settings.outline_color = Color(0.0, 0.0, 0.0, 0.65)
	label.label_settings = settings

	parent.add_child(label)
	return label


func _result_text() -> String:
	var result: Dictionary = _replay.get("result", {})
	var winner_id: Variant = result.get("winner_id")
	if bool(result.get("is_draw", false)) or winner_id == null:
		return "DRAW"
	for meta in _fighter_meta:
		if int(meta.get("id", -1)) == int(winner_id):
			return "WINNER: %s" % str(meta.get("name", "?"))
	return "DRAW"


# --- playback ------------------------------------------------------------

func _apply_playhead(playhead: float) -> void:
	_playhead = playhead

	var index := int(floor(playhead))
	var next_index := mini(index + 1, _frames.size() - 1)
	var blend := playhead - float(index)

	var frame: Dictionary = _frames[index]
	var current: Array = frame.get("fighters", [])
	var upcoming: Array = (_frames[next_index] as Dictionary).get("fighters", [])

	for i in _spheres.size():
		if i >= current.size():
			continue
		var now: Dictionary = current[i]
		var soon: Dictionary = upcoming[i] if i < upcoming.size() else now

		# Interpolation is cosmetic: the replay data is never modified.
		var x := lerpf(float(now.get("x", 0.0)), float(soon.get("x", 0.0)), blend)
		var y := lerpf(float(now.get("y", 0.0)), float(soon.get("y", 0.0)), blend)
		var health := lerpf(float(now.get("health", 0.0)), float(soon.get("health", 0.0)), blend)
		var radius := to_units(float((_fighter_meta[i] as Dictionary).get("radius", 40.0)))

		_spheres[i].position = to_world(x, y, radius)
		var alive := bool(now.get("alive", true))
		_spheres[i].material_override = _live_materials[i] if alive else _dead_materials[i]

		_update_health_row(i, health)

	_update_timer(int(frame.get("tick", 0)))
	_result_label.visible = playhead >= float(_frames.size() - 1)


func _update_health_row(index: int, health: float) -> void:
	if index >= _health_fills.size():
		return
	var max_health := maxf(1.0, float((_fighter_meta[index] as Dictionary).get("max_health", 100.0)))
	var fraction := clampf(health / max_health, 0.0, 1.0)
	_health_fills[index].size = Vector2(HEALTH_BAR_SIZE.x * fraction, HEALTH_BAR_SIZE.y)
	_health_labels[index].text = "%d HP" % int(round(health))


func _update_timer(tick: int) -> void:
	var limit := float(_replay.get("limit_seconds", 35.0))
	var hz := maxf(1.0, float(_replay.get("physics_hz", 120.0)))
	_timer_label.text = "%.1f" % maxf(0.0, limit - float(tick) / hz)
