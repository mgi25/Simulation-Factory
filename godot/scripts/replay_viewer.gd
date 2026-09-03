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

# The only replay schema this viewer understands. Anything older is rejected
# with a message rather than half-played.
const REPLAY_VERSION := 4

const FLOOR_THICKNESS := 0.25
const WALL_HEIGHT := 0.9
const WALL_THICKNESS := 0.16
const WALL_TRIM_HEIGHT := 0.07
const WALL_TRIM_OVERHANG := 0.06

# The plinth the arena stands on. It reaches past the walls so the portrait
# frame reads as a stage in a dark room rather than a rectangle floating in
# black, and it is what fills the space the arena itself cannot reach.
const STAGE_APRON := 1.05
const STAGE_DROP := 0.14

# One restrained slate accent for every piece of arena chrome. Competitor
# colour belongs to fighters, powers and combat, never to the furniture, and
# nothing here is ever allowed to outshine a Pulse bolt or an impact ring.
const ACCENT_COLOR := Color(0.44, 0.50, 0.64)
const MARKING_HEIGHT := 0.014
const MARKING_WIDTH := 0.055
const MARKING_INSET := 0.52
const MARKING_EMISSION := 0.42
const CENTRE_RING_RADIUS := 1.30
const CENTRE_DOT_RADIUS := 0.17
const RIM_EMISSION := 0.55
const RIM_HEIGHT := 0.05
const RIM_DROP := 0.14

# Nearly overhead: the arena is deeper than it is wide, and a portrait frame
# only gets its height back by looking down on it. Still angled enough to keep
# real perspective, sphere volume and cast shadows.
const CAMERA_FOV := 50.0
const CAMERA_ELEVATION_DEG := 78.0
const CAMERA_MARGIN := 0.15

# Rush trail: ghost copies sampled from earlier replay frames, so the effect
# is driven purely by exported state and needs no particle system.
const RUSH_TRAIL_COUNT := 6
const RUSH_TRAIL_FRAME_STEP := 2
const POWER_EMISSION_ENERGY := 0.85

# Temporary entities read as energy: bright and self-lit, but still the
# owner's colour - past roughly 2.0 the tonemapper clips them to white and
# they stop belonging to anyone. The height bias lifts a small projectile to
# about fighter-centre height so it reads as flying at its target rather
# than rolling along the floor.
const ENTITY_EMISSION_ENERGY := 1.6
const ENTITY_HEIGHT_BIAS := 3.0

# An Echo clone is a ghost of its owner: translucent, softly lit and ringed,
# so a glance separates it from a hard, bright Pulse bolt. It sits at its own
# radius like a fighter, because it rolls around the floor like one.
const CLONE_EMISSION_ENERGY := 0.9
const CLONE_ALPHA := 0.30
const CLONE_RIM_AMOUNT := 1.0

# An Orbit satellite is a hot little bead: a near-white core inside an
# owner-coloured glow, glossy rather than matte. Distinct from a Pulse bolt,
# which is the owner's colour all the way through, and from an Echo ghost,
# which is translucent and pale.
const ORB_EMISSION_ENERGY := 2.2
const ORB_CORE_LIGHTEN := 0.45

const CombatVFX := preload("res://scripts/combat_vfx.gd")
const BattleHud := preload("res://scripts/battle_hud.gd")

var _replay: Dictionary = {}
var _frames: Array = []
var _fighter_meta: Array = []

var _arena_center := Vector2.ZERO
var _arena_units := Vector2.ONE

var _spheres: Array[MeshInstance3D] = []
var _live_materials: Array[StandardMaterial3D] = []
var _dead_materials: Array[StandardMaterial3D] = []
var _active_materials: Array[StandardMaterial3D] = []
var _base_radius_units: Array[float] = []
var _power_names: Array[String] = []
var _trails: Array = []

var _hud: CanvasLayer
# Per-fighter presentation state, refreshed from the frames every tick and
# handed to the overlay: the HUD reads the battle, it never guesses at it.
var _healths: Array[float] = []
var _powered: Array[bool] = []

# Dynamic entity visuals, keyed by the replay's entity id. Nodes are created
# when an id first appears and freed when it stops appearing, so the scene
# holds exactly the entities the current frame describes.
var _entity_nodes: Dictionary = {}
var _entity_materials: Dictionary = {}
var _entity_root: Node3D
var _entity_mesh: SphereMesh

var _vfx: Node3D

var _playhead := 0.0
# The authoritative playback clock, in simulation ticks. Frames are sampled
# from it and every visual effect is aged against it, so nothing on screen is
# timed by wall-clock seconds. It keeps advancing once the last frame is
# reached, which is what lets a final elimination flash finish and clear.
var _replay_tick := 0.0
var _physics_hz := 120.0
var _ticks_per_frame := 2.0


func _ready() -> void:
	var path := _resolve_path(_replay_path_argument())
	if not _load_replay(path):
		var error_hud := BattleHud.new()
		add_child(error_hud)
		error_hud.show_error("No replay at
%s" % path)
		return

	_read_arena()
	_build_environment()
	_build_lights()
	_build_camera()
	_build_arena()
	_build_fighters()
	_build_entity_pool()
	_build_vfx()
	_build_hud()
	_apply_playhead(0.0)
	_vfx.update_to_tick(0.0)
	_hud.update_hud(0.0, _healths, _powered)

	print("replay loaded: seed=%d frames=%d duration=%.2fs" % [
		int(_replay.get("seed", 0)),
		_frames.size(),
		float(_replay.get("result", {}).get("duration", 0.0)),
	])


func _process(delta: float) -> void:
	if _frames.size() < 2:
		return
	# One clock drives everything: real time advances the replay tick, the
	# replay tick decides which frames to blend and how old each effect is.
	_replay_tick += delta * _physics_hz
	var last := float(_frames.size() - 1)
	_apply_playhead(minf(_replay_tick / _ticks_per_frame, last))
	_vfx.update_to_tick(_replay_tick)
	# The overlay is driven by the raw tick, not the clamped playhead: the
	# result panel has to keep animating after the last frame is reached.
	_hud.update_hud(_replay_tick, _healths, _powered)


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
	if int(data.get("version", 0)) != REPLAY_VERSION:
		push_error("Unsupported replay version: %s (expected %d)" % [
			str(data.get("version")), REPLAY_VERSION])
		return false

	var frames: Array = data.get("frames", [])
	var fighters: Array = data.get("fighters", [])
	if frames.is_empty() or fighters.is_empty():
		push_error("Replay contains no frames or no fighters: %s" % path)
		return false

	_replay = data
	_frames = frames
	_fighter_meta = fighters
	_physics_hz = maxf(1.0, float(data.get("physics_hz", 120.0)))
	_ticks_per_frame = maxf(1.0, float(data.get("ticks_per_frame", 2.0)))
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
	sky_material.ground_horizon_color = Color(0.13, 0.145, 0.20)
	sky_material.ground_bottom_color = Color(0.055, 0.06, 0.09)

	var sky := Sky.new()
	sky.sky_material = sky_material

	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_sky_contribution = 1.0
	environment.ambient_light_energy = 0.62
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	# Restrained glow: highlights pop without washing the arena out.
	environment.glow_enabled = true
	environment.glow_intensity = 0.25
	environment.glow_bloom = 0.02
	environment.glow_hdr_threshold = 1.1
	environment.ssao_enabled = true
	environment.ssao_radius = 0.6
	environment.ssao_intensity = 1.2

	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	world.environment = environment
	add_child(world)


func _build_lights() -> void:
	var key := DirectionalLight3D.new()
	key.name = "KeyLight"
	key.light_color = Color(1.0, 0.97, 0.92)
	key.light_energy = 1.5
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	key.directional_shadow_max_distance = 60.0
	key.shadow_bias = 0.04
	# Yaw past 180 degrees so the light travels towards the camera and the
	# sphere shadows land in front of them instead of hiding behind them.
	key.rotation_degrees = Vector3(-64.0, 202.0, 0.0)
	add_child(key)

	var fill := DirectionalLight3D.new()
	fill.name = "FillLight"
	fill.light_color = Color(0.70, 0.79, 1.0)
	fill.light_energy = 0.38
	fill.shadow_enabled = false
	fill.rotation_degrees = Vector3(-22.0, 30.0, 0.0)
	add_child(fill)


func _build_camera() -> void:
	var camera := Camera3D.new()
	camera.name = "Camera3D"
	camera.fov = CAMERA_FOV
	camera.near = 0.1
	camera.far = 300.0

	# Vertical 9:16 framing. Looking down at the arena centre from elevation e,
	# a floor point at depth z sits `distance - z * cos(e)` along the view
	# axis, so the *near* edge is the widest thing on screen and the one the
	# horizontal field of view has to accommodate. Fitting the near edge
	# rather than the centre is what keeps the closest corners on screen, and
	# it is why the arena can be framed this tightly.
	var viewport_width := float(ProjectSettings.get_setting(
		"display/window/size/viewport_width", 1080))
	var viewport_height := float(ProjectSettings.get_setting(
		"display/window/size/viewport_height", 1920))
	var half_v := deg_to_rad(CAMERA_FOV * 0.5)
	var half_h := atan(tan(half_v) * viewport_width / viewport_height)
	var elevation := deg_to_rad(CAMERA_ELEVATION_DEG)
	var half_depth := _arena_units.y * 0.5

	var fit_width := (_arena_units.x * 0.5 + CAMERA_MARGIN) / tan(half_h) \
		+ half_depth * cos(elevation)
	# The far edge has to clear the top of the frame too. At this elevation
	# the width is what binds, but a squarer arena would not be.
	var fit_depth := (half_depth * sin(elevation) + CAMERA_MARGIN) / tan(half_v) \
		- half_depth * cos(elevation)
	var distance := maxf(fit_width, fit_depth)

	camera.position = Vector3(0.0, distance * sin(elevation), distance * cos(elevation))
	add_child(camera)
	camera.look_at(Vector3.ZERO, Vector3.UP)


func _build_arena() -> void:
	var half := _arena_units * 0.5
	var outer_x := _arena_units.x + WALL_THICKNESS * 2.0
	var outer_z := _arena_units.y + WALL_THICKNESS * 2.0

	_build_stage(outer_x, outer_z)
	_build_floor(outer_x, outer_z)
	_build_markings(half)
	_build_walls(half, outer_x, outer_z)


func _build_stage(outer_x: float, outer_z: float) -> void:
	## A plinth reaching past the walls. It is what the frame shows to either
	## side of the arena, so the portrait crop reads as a lit stage in a dark
	## room rather than a rectangle stranded in black.
	var mesh := BoxMesh.new()
	mesh.size = Vector3(
		outer_x + STAGE_APRON * 2.0, FLOOR_THICKNESS,
		outer_z + STAGE_APRON * 2.0)

	var node := MeshInstance3D.new()
	node.name = "Stage"
	node.mesh = mesh
	node.material_override = _make_material(Color(0.105, 0.115, 0.145), 0.0, 0.85, 0.15)
	node.position = Vector3(0.0, -STAGE_DROP - FLOOR_THICKNESS * 0.5, 0.0)
	add_child(node)


func _build_floor(outer_x: float, outer_z: float) -> void:
	var mesh := BoxMesh.new()
	mesh.size = Vector3(outer_x, FLOOR_THICKNESS, outer_z)

	var node := MeshInstance3D.new()
	node.name = "Floor"
	node.mesh = mesh
	# Matte floor: with the key light behind the camera, any gloss here would
	# mirror it straight back and wash the arena out.
	node.material_override = _make_material(Color(0.225, 0.235, 0.285), 0.05, 0.74, 0.22)
	node.position = Vector3(0.0, -FLOOR_THICKNESS * 0.5, 0.0)
	add_child(node)


func _build_markings(half: Vector2) -> void:
	## Three pieces only - an inset border, a centre ring and a centre mark -
	## lit dimly enough that they never compete with a projectile or a hit.
	var material := _make_emissive(ACCENT_COLOR, MARKING_EMISSION, 0.55)
	var inset := Vector2(half.x - MARKING_INSET, half.y - MARKING_INSET)

	var strips := [
		[Vector3(inset.x * 2.0, MARKING_HEIGHT, MARKING_WIDTH), Vector3(0.0, 0.0, -inset.y)],
		[Vector3(inset.x * 2.0, MARKING_HEIGHT, MARKING_WIDTH), Vector3(0.0, 0.0, inset.y)],
		[Vector3(MARKING_WIDTH, MARKING_HEIGHT, inset.y * 2.0), Vector3(-inset.x, 0.0, 0.0)],
		[Vector3(MARKING_WIDTH, MARKING_HEIGHT, inset.y * 2.0), Vector3(inset.x, 0.0, 0.0)],
	]
	for index in strips.size():
		var mesh := BoxMesh.new()
		mesh.size = strips[index][0]
		_add_decor("Border%d" % index, mesh, strips[index][1], material)

	var ring := TorusMesh.new()
	ring.inner_radius = CENTRE_RING_RADIUS - MARKING_WIDTH
	ring.outer_radius = CENTRE_RING_RADIUS
	ring.rings = 64
	ring.ring_segments = 6
	_add_decor("CentreRing", ring, Vector3.ZERO, material)

	var dot := CylinderMesh.new()
	dot.top_radius = CENTRE_DOT_RADIUS
	dot.bottom_radius = CENTRE_DOT_RADIUS
	dot.height = MARKING_HEIGHT
	dot.radial_segments = 32
	_add_decor("CentreMark", dot, Vector3.ZERO, material)


func _add_decor(piece: String, mesh: Mesh, position: Vector3,
		material: StandardMaterial3D) -> void:
	var node := MeshInstance3D.new()
	node.name = piece
	node.mesh = mesh
	node.material_override = material
	# Flush with the floor and casting nothing: a marking is paint, not an
	# object standing on the arena.
	node.position = position + Vector3(0.0, MARKING_HEIGHT * 0.5, 0.0)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(node)


func _build_walls(half: Vector2, outer_x: float, outer_z: float) -> void:
	## Wall inner faces sit exactly on the arena bounds, like the Pymunk walls.
	## Everything added on top of that - the capping rail and the lit inner
	## rim - is decoration, and none of it changes where anything bounces.
	var body := _make_material(Color(0.175, 0.19, 0.245), 0.10, 0.68, 0.30)
	var trim := _make_material(Color(0.215, 0.235, 0.30), 0.15, 0.62, 0.32)
	var rim := _make_emissive(ACCENT_COLOR, RIM_EMISSION, 0.4)

	var wall_y := WALL_HEIGHT * 0.5
	var wall_x := half.x + WALL_THICKNESS * 0.5
	var wall_z := half.y + WALL_THICKNESS * 0.5
	var side := Vector3(WALL_THICKNESS, WALL_HEIGHT, outer_z)
	var end := Vector3(outer_x, WALL_HEIGHT, WALL_THICKNESS)

	var walls := [
		["Left", side, Vector3(-wall_x, wall_y, 0.0), Vector3(1.0, 0.0, 0.0)],
		["Right", side, Vector3(wall_x, wall_y, 0.0), Vector3(-1.0, 0.0, 0.0)],
		["Top", end, Vector3(0.0, wall_y, -wall_z), Vector3(0.0, 0.0, 1.0)],
		["Bottom", end, Vector3(0.0, wall_y, wall_z), Vector3(0.0, 0.0, -1.0)],
	]
	for wall in walls:
		var piece: String = wall[0]
		var size: Vector3 = wall[1]
		var position: Vector3 = wall[2]
		var inward: Vector3 = wall[3]

		var mesh := BoxMesh.new()
		mesh.size = size
		_add_wall_piece("Wall" + piece, mesh, position, body)

		# A capping rail, standing slightly proud of both faces.
		var cap := BoxMesh.new()
		cap.size = Vector3(
			size.x + absf(inward.x) * WALL_TRIM_OVERHANG,
			WALL_TRIM_HEIGHT,
			size.z + absf(inward.z) * WALL_TRIM_OVERHANG)
		_add_wall_piece("Trim" + piece, cap,
			Vector3(position.x, WALL_HEIGHT + WALL_TRIM_HEIGHT * 0.5, position.z), trim)

		# A thin lit line under the rail, on the inside face only, so the arena
		# has a defined edge without the walls glowing at the viewer.
		var strip := BoxMesh.new()
		strip.size = Vector3(
			0.03 if absf(inward.x) > 0.5 else size.x,
			RIM_HEIGHT,
			0.03 if absf(inward.z) > 0.5 else size.z)
		var strip_position := position + inward * (WALL_THICKNESS * 0.5 + 0.015)
		strip_position.y = WALL_HEIGHT - RIM_DROP
		_add_wall_piece("Rim" + piece, strip, strip_position, rim, false)


func _add_wall_piece(piece: String, mesh: Mesh, position: Vector3,
		material: StandardMaterial3D, shadows := true) -> void:
	var node := MeshInstance3D.new()
	node.name = piece
	node.mesh = mesh
	node.material_override = material
	node.position = position
	if not shadows:
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(node)


func _build_fighters() -> void:
	## The sphere mesh is built at the fighter's base radius; per-frame growth
	## arrives as node scale, so Titan never rebuilds a mesh at runtime.
	for meta in _fighter_meta:
		var radius := to_units(float(meta.get("radius", 40.0)))
		var color := _color_of(meta)
		var power := str(meta.get("power", "none"))

		var mesh := SphereMesh.new()
		mesh.radius = radius
		mesh.height = radius * 2.0
		mesh.radial_segments = 48
		mesh.rings = 24

		var live := _make_material(color, 0.40, 0.22)
		var dead := _make_material(color.darkened(0.72), 0.15, 0.7)
		# Cached up front: showing a power is a material swap per frame, never
		# a fresh allocation. Emissive but still recognisably the fighter's
		# colour - any brighter and both spheres blow out to white.
		var powered := _make_material(color, 0.30, 0.18)
		powered.emission_enabled = true
		powered.emission = color
		powered.emission_energy_multiplier = POWER_EMISSION_ENERGY

		var node := MeshInstance3D.new()
		node.name = "Fighter%s" % str(meta.get("id", 0))
		node.mesh = mesh
		node.material_override = live
		node.position = to_world(_arena_center.x, _arena_center.y, radius)
		add_child(node)

		_spheres.append(node)
		_live_materials.append(live)
		_dead_materials.append(dead)
		_active_materials.append(powered)
		_base_radius_units.append(radius)
		_power_names.append(power)
		_trails.append(_build_trail(mesh, color, power))


func _build_entity_pool() -> void:
	## One shared unit sphere for every temporary entity; per-entity size comes
	## from the replay and is applied as node scale.
	_entity_root = Node3D.new()
	_entity_root.name = "DynamicEntities"
	add_child(_entity_root)

	_entity_mesh = SphereMesh.new()
	_entity_mesh.radius = 1.0
	_entity_mesh.height = 2.0
	_entity_mesh.radial_segments = 20
	_entity_mesh.rings = 10


func _build_vfx() -> void:
	## Combat feedback lives under its own node, so a temporary flash is never
	## mistaken for a fighter, an entity or part of the HUD.
	_vfx = CombatVFX.new()
	_vfx.name = "VFXRoot"
	add_child(_vfx)

	var colors: Array[Color] = []
	for meta in _fighter_meta:
		colors.append(_color_of(meta))

	_vfx.configure(colors, get_node_or_null("Camera3D"), _physics_hz, to_world)
	_vfx.set_events(_replay.get("events", []))


func _entity_material(kind: String, color: Color) -> StandardMaterial3D:
	## Cached per (type, colour): entities come and go every second, so this
	## must never allocate per frame.
	var key := "%s:%d" % [kind, color.to_rgba32()]
	if _entity_materials.has(key):
		return _entity_materials[key]

	var material: StandardMaterial3D
	if kind == "echo":
		material = _make_clone_material(color)
	elif kind == "orbit":
		material = _make_orb_material(color)
	else:
		material = _make_projectile_material(color)
	_entity_materials[key] = material
	return material


func _make_projectile_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = 0.0
	material.roughness = 0.35
	material.emission_enabled = true
	material.emission = color
	material.emission_energy_multiplier = ENTITY_EMISSION_ENERGY
	return material


func _make_orb_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color.lightened(ORB_CORE_LIGHTEN)
	material.metallic = 0.0
	material.roughness = 0.1
	material.emission_enabled = true
	material.emission = color
	material.emission_energy_multiplier = ORB_EMISSION_ENERGY
	return material


func _make_clone_material(color: Color) -> StandardMaterial3D:
	## A hollow shell of light: additive over the dark floor so the arena
	## shows through it, with a hot edge where the sphere turns away. Reads as
	## an apparition rather than a solid ball, and nothing like a Pulse bolt.
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	material.albedo_color = Color(color.r, color.g, color.b, CLONE_ALPHA)
	material.metallic = 0.0
	material.roughness = 0.55
	material.emission_enabled = true
	material.emission = color.lightened(0.45)
	material.emission_energy_multiplier = CLONE_EMISSION_ENERGY
	# Grazing angles glow, so the silhouette is an outline, not a surface.
	material.rim_enabled = true
	material.rim = CLONE_RIM_AMOUNT
	material.rim_tint = 0.0
	return material


func _build_trail(mesh: SphereMesh, color: Color, power: String) -> Array:
	## Rush only: a handful of additive ghosts that replay earlier positions.
	var ghosts: Array = []
	if power != "rush":
		return ghosts
	for k in RUSH_TRAIL_COUNT:
		var fade := 1.0 - float(k) / float(RUSH_TRAIL_COUNT)
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		material.albedo_color = Color(color.r, color.g, color.b, 0.26 * fade)

		var ghost := MeshInstance3D.new()
		ghost.name = "Trail%d" % k
		ghost.mesh = mesh
		ghost.material_override = material
		ghost.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		ghost.visible = false
		add_child(ghost)
		ghosts.append(ghost)
	return ghosts


func _make_material(color: Color, metallic: float, roughness: float,
		specular := 0.6) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = metallic
	material.metallic_specular = specular
	material.roughness = roughness
	return material


func _make_emissive(color: Color, energy: float,
		darken := 0.0) -> StandardMaterial3D:
	## Arena chrome: lit enough to be seen, kept well under the glow threshold
	## so nothing decorative ever blooms the way a hit or a projectile does.
	var material := _make_material(color.darkened(darken), 0.0, 0.55, 0.3)
	material.emission_enabled = true
	material.emission = color
	material.emission_energy_multiplier = energy
	return material


func _color_of(meta: Dictionary) -> Color:
	var raw: Variant = meta.get("color", [])
	if raw is Array and (raw as Array).size() >= 3:
		var rgb: Array = raw
		return Color8(int(rgb[0]), int(rgb[1]), int(rgb[2]))
	return Color.WHITE


# --- HUD -----------------------------------------------------------------

func _build_hud() -> void:
	## The overlay owns its own layout, animation and timing; the viewer only
	## tells it what the current frame says.
	_hud = BattleHud.new()
	_hud.name = "HUD"
	add_child(_hud)
	_hud.configure(_replay)
	_hud.set_events(_replay.get("events", []))

	for _meta in _fighter_meta:
		_healths.append(0.0)
		_powered.append(false)


# --- playback ------------------------------------------------------------

func _apply_playhead(playhead: float) -> void:
	_playhead = playhead

	var index := int(floor(playhead))
	var next_index := mini(index + 1, _frames.size() - 1)
	var blend := playhead - float(index)

	var frame: Dictionary = _frames[index]
	var next_frame: Dictionary = _frames[next_index]
	var current: Array = frame.get("fighters", [])
	var upcoming: Array = next_frame.get("fighters", [])
	var current_entities: Array = frame.get("entities", [])
	var upcoming_entities: Array = next_frame.get("entities", [])

	for i in _spheres.size():
		if i >= current.size():
			continue
		var now: Dictionary = current[i]
		var soon: Dictionary = upcoming[i] if i < upcoming.size() else now

		# Interpolation is cosmetic: the replay data is never modified.
		var x := lerpf(float(now.get("x", 0.0)), float(soon.get("x", 0.0)), blend)
		var y := lerpf(float(now.get("y", 0.0)), float(soon.get("y", 0.0)), blend)
		var health := lerpf(float(now.get("health", 0.0)), float(soon.get("health", 0.0)), blend)
		# Radius is per-frame replay state now, not static metadata: Titan's
		# size is decided in Python and only displayed here.
		var radius := to_units(lerpf(
			float(now.get("radius", 40.0)), float(soon.get("radius", 40.0)), blend))
		var alive := bool(now.get("alive", true))
		var powered := alive and bool(now.get("power_active", false))

		_spheres[i].position = to_world(x, y, radius)
		_spheres[i].scale = Vector3.ONE * (radius / maxf(0.001, _base_radius_units[i]))
		if not alive:
			_spheres[i].material_override = _dead_materials[i]
		elif powered:
			_spheres[i].material_override = _active_materials[i]
		else:
			_spheres[i].material_override = _live_materials[i]

		_update_trail(i, index, powered)
		_healths[i] = health
		_powered[i] = powered

	_update_entities(current_entities, upcoming_entities, blend)


func _update_entities(current: Array, upcoming: Array, blend: float) -> void:
	## Entities are addressed by replay id, so one appearing or disappearing
	## between frames is normal rather than an error.
	var next_by_id := {}
	for raw in upcoming:
		var soon: Dictionary = raw
		next_by_id[int(soon.get("id", -1))] = soon

	var seen := {}
	for raw in current:
		var now: Dictionary = raw
		var id := int(now.get("id", -1))
		seen[id] = true

		var kind := str(now.get("type", "entity"))
		var node: MeshInstance3D = _entity_nodes.get(id)
		if node == null:
			node = MeshInstance3D.new()
			node.name = "Entity%d" % id
			node.mesh = _entity_mesh
			node.material_override = _entity_material(kind, _color_of(now))
			node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			_entity_root.add_child(node)
			_entity_nodes[id] = node

		# Interpolation is cosmetic and only possible while the entity exists
		# in both frames; on its last frame it simply holds still.
		var x := float(now.get("x", 0.0))
		var y := float(now.get("y", 0.0))
		if next_by_id.has(id):
			var soon: Dictionary = next_by_id[id]
			x = lerpf(x, float(soon.get("x", x)), blend)
			y = lerpf(y, float(soon.get("y", y)), blend)

		var radius := to_units(float(now.get("radius", 8.0)))
		# A clone is fighter-sized and sits on the floor like one; a small
		# bolt is lifted so it reads as flying rather than rolling.
		var height := radius if kind == "echo" else radius * ENTITY_HEIGHT_BIAS
		node.scale = Vector3.ONE * radius
		node.position = to_world(x, y, height)

	for id in _entity_nodes.keys():
		if not seen.has(id):
			(_entity_nodes[id] as Node).queue_free()
			_entity_nodes.erase(id)


func _update_trail(fighter: int, index: int, powered: bool) -> void:
	var ghosts: Array = _trails[fighter]
	for k in ghosts.size():
		var ghost: MeshInstance3D = ghosts[k]
		var source := index - (k + 1) * RUSH_TRAIL_FRAME_STEP
		if not powered or source < 0:
			ghost.visible = false
			continue

		var past_frame: Dictionary = _frames[source]
		var past_list: Array = past_frame.get("fighters", [])
		if fighter >= past_list.size():
			ghost.visible = false
			continue

		# A ghost only shows where the power was already active, so the trail
		# grows out of the burst instead of snapping into place.
		var past: Dictionary = past_list[fighter]
		if not bool(past.get("power_active", false)):
			ghost.visible = false
			continue

		var radius := to_units(float(past.get("radius", 40.0)))
		ghost.position = to_world(
			float(past.get("x", 0.0)), float(past.get("y", 0.0)), radius)
		ghost.scale = Vector3.ONE * (radius / maxf(0.001, _base_radius_units[fighter]))
		ghost.visible = true
