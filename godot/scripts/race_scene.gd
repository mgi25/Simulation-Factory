extends Node3D

## Plays back a race replay exported by the Python simulation.
##
## The sibling of the battle path in `replay_viewer.gd`, and it keeps the same
## contract: Godot is presentation only. It runs no physics and no race rules.
## Every position, every arm angle, every rank and the whole result come out of
## the replay file, and the course is rebuilt from the geometry the replay
## carries rather than by importing anything that knows how a course is built.
##
## Two things about a race make it a different scene rather than the same one
## with different meshes.
##
## The course is taller than the frame - six thousand pixels against nineteen
## hundred - so the camera has to travel, where a duel's never moves. It does
## not decide where to travel: the replay records the camera track the Python
## preview actually used, and this reads it, so a rendered frame shows what a
## viewer of the live preview would have seen at that moment rather than what
## a second implementation of the follow logic would have chosen.
##
## And the camera looks straight down through an orthographic projection,
## where the duel's is a perspective camera at 78 degrees. That is a deliberate
## choice for V0.2 rather than a style: an orthographic top-down view maps
## simulation pixels to frame pixels exactly, so a rendered frame can be
## compared against the Python preview position by position. Correct playback
## is the goal at this stage; the look comes later.

# The single place where logical simulation pixels become Godot world units.
# The same figure the battle scene uses.
const PIXELS_PER_UNIT := 100.0

# The frame, in simulation pixels. The camera track in the replay is the
# course y at the *top* of this window, so the two have to agree.
const VIEW_HEIGHT := 1920.0

# Orthographic half-height in world units, and how far above the plane the
# camera sits. With an orthographic projection the height changes nothing
# about the picture - it is only far enough that nothing clips.
const CAMERA_SIZE := VIEW_HEIGHT / PIXELS_PER_UNIT
const CAMERA_HEIGHT := 40.0

# How thick the course reads. Everything is a slab lying on the plane, lit
# from above, so depth is only there to give the pieces an edge and a shadow.
const FLOOR_DROP := 0.06
const PIECE_HEIGHT := 0.34
const PEG_HEIGHT := 0.42
const SPINNER_HUB_HEIGHT := 0.50
const SPINNER_ARM_HEIGHT := 0.46
const BACKING_INSET := 0.0

# Course palette. The roles a racer has to tell apart at a glance get
# distinct hues; everything structural stays slate.
const BACKING_COLOR := Color(0.055, 0.060, 0.080)
const WALL_COLOR := Color(0.155, 0.170, 0.215)
const RAMP_COLOR := Color(0.235, 0.255, 0.320)
const RAMP_SLICK_COLOR := Color(0.275, 0.310, 0.400)
const PEG_COLOR := Color(0.235, 0.400, 0.640)
const GATE_COLOR := Color(0.640, 0.235, 0.235)
const PAD_COLOR := Color(0.250, 0.640, 0.380)
const SPINNER_COLOR := Color(0.660, 0.400, 0.180)
const SPINNER_HUB_COLOR := Color(0.440, 0.270, 0.130)
const FINISH_COLOR := Color(0.820, 0.780, 0.320)
const CHECKPOINT_COLOR := Color(0.200, 0.300, 0.270)

const ACCENT_EMISSION := 0.30
const FINISH_EMISSION := 0.55
const FINISH_BAR_HEIGHT := 0.05
const FINISH_BAR_THICKNESS := 0.10

# A finished racer stays in the world - a winner that vanished on crossing
# the line would be no use to an edit - but it stops being a competitor, so
# it is dimmed rather than removed.
const FINISHED_DIM := 0.45

# How near a whole frame the playhead has to be to *be* that frame. Sample
# times are computed by dividing and multiplying, and floating point lands
# either side of the integer, so frame 123 can arrive as 122.99999999999999.
const PLAYHEAD_SNAP := 1.0e-6

const RaceHud := preload("res://scripts/race_hud.gd")

var _replay: Dictionary = {}
var _course: Dictionary = {}
var _frames: Array = []
var _racer_meta: Array = []

var _course_width := 1080.0

var _camera: Camera3D
var _hud: CanvasLayer

var _racer_nodes: Array[MeshInstance3D] = []
var _racer_live: Array[StandardMaterial3D] = []
var _racer_done: Array[StandardMaterial3D] = []
var _racer_radius: Array[float] = []

# Pivots of the spinners, keyed by the replay's spinner id. Built once from
# the course; every frame writes a transform into them and nothing is ever
# created or freed while playing back.
var _spinner_pivots: Dictionary = {}
# Gate pieces, hidden the frame the countdown ends. Removal is a state in the
# replay, not something timed here.
var _gate_nodes: Array[Node3D] = []
var _gates_hidden := false

var _physics_hz := 120.0
var _ticks_per_frame := 2.0


func build(replay: Dictionary) -> void:
	_replay = replay
	_course = replay.get("course", {})
	_frames = replay.get("frames", [])
	_racer_meta = replay.get("racers", [])
	_course_width = maxf(1.0, float(_course.get("width", 1080.0)))
	_physics_hz = maxf(1.0, float(replay.get("physics_hz", 120.0)))
	_ticks_per_frame = maxf(1.0, float(replay.get("ticks_per_frame", 2.0)))

	_build_environment()
	_build_lights()
	_build_camera()
	_build_backing()
	_build_pieces()
	_build_spinners()
	_build_finish_line()
	_build_racers()
	_build_hud()


func present(tick: float) -> void:
	## Show the race as it stood at `tick`, in simulation ticks.
	if _frames.size() < 1:
		return
	var last := float(_frames.size() - 1)
	var playhead := clampf(tick / _ticks_per_frame, 0.0, last)
	var whole := roundf(playhead)
	if absf(playhead - whole) < PLAYHEAD_SNAP:
		playhead = whole

	var index := int(floor(playhead))
	var next_index := mini(index + 1, _frames.size() - 1)
	var blend := playhead - float(index)

	var frame: Dictionary = _frames[index]
	var next_frame: Dictionary = _frames[next_index]

	_update_camera(frame, next_frame, blend)
	_update_racers(frame.get("racers", []), next_frame.get("racers", []), blend)
	_update_spinners(frame.get("spinners", []), next_frame.get("spinners", []), blend)
	_update_gates(frame)
	_hud.update_hud(frame, tick)


# --- coordinate conversion -----------------------------------------------

func to_world(sim_x: float, sim_y: float, height: float) -> Vector3:
	## Simulation x maps to world X, simulation y to world Z, Y is visual only.
	##
	## X is centred on the course so the camera can sit on the middle line and
	## only ever move along Z. Z is *not* centred: it is the course height
	## itself, which is what lets the camera track be read straight out of the
	## replay without an offset in between.
	return Vector3(
		(sim_x - _course_width * 0.5) / PIXELS_PER_UNIT,
		height,
		sim_y / PIXELS_PER_UNIT)


func to_units(pixels: float) -> float:
	return pixels / PIXELS_PER_UNIT


# --- scene construction --------------------------------------------------

func _build_environment() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.040, 0.055)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.55, 0.60, 0.72)
	environment.ambient_light_energy = 0.75
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	environment.glow_enabled = true
	environment.glow_intensity = 0.22
	environment.glow_bloom = 0.02
	environment.glow_hdr_threshold = 1.1

	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	world.environment = environment
	add_child(world)


func _build_lights() -> void:
	## Two directionals, both angled across the course rather than down it.
	##
	## The camera looks straight down, so a light from directly above would
	## put every shadow underneath the thing casting it and the course would
	## read as flat paint. Tilting the key sideways is what gives a ramp an
	## edge and a racer a shadow to sit on.
	var key := DirectionalLight3D.new()
	key.name = "KeyLight"
	key.light_color = Color(1.0, 0.97, 0.92)
	key.light_energy = 1.35
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	key.directional_shadow_max_distance = 80.0
	key.shadow_bias = 0.03
	key.rotation_degrees = Vector3(-58.0, 34.0, 0.0)
	add_child(key)

	var fill := DirectionalLight3D.new()
	fill.name = "FillLight"
	fill.light_color = Color(0.70, 0.79, 1.0)
	fill.light_energy = 0.40
	fill.shadow_enabled = false
	fill.rotation_degrees = Vector3(-38.0, -140.0, 0.0)
	add_child(fill)


func _build_camera() -> void:
	## Orthographic, straight down, framing exactly 1080x1920 course pixels.
	##
	## `size` is the vertical extent in world units because the aspect is kept
	## on height, so 19.2 units of course fill the 1920 pixel frame and the
	## 10.8 units of width fall out of the 9:16 aspect exactly. One simulation
	## pixel is one frame pixel, everywhere in the frame - which is the whole
	## reason this is not a perspective camera. Under perspective, a racer
	## standing 0.3 units above the plane at the edge of the frame would sit
	## eight pixels away from where the simulation put it.
	_camera = Camera3D.new()
	_camera.name = "Camera3D"
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.size = CAMERA_SIZE
	_camera.near = 0.1
	_camera.far = CAMERA_HEIGHT * 3.0
	# Looking down -Y with screen-up along -Z, so up the frame is up the
	# course. Set as a rotation rather than with look_at, which has no way to
	# express "up" for a straight-down view.
	_camera.rotation_degrees = Vector3(-90.0, 0.0, 0.0)
	_camera.position = Vector3(0.0, CAMERA_HEIGHT, 0.0)
	add_child(_camera)


func _build_backing() -> void:
	## A dark slab behind the whole course, so the frame is a lit stage rather
	## than pieces floating in the background colour.
	var top := float(_course.get("top", 0.0))
	var bottom := float(_course.get("bottom", 0.0))
	var mesh := BoxMesh.new()
	mesh.size = Vector3(
		to_units(_course_width) + BACKING_INSET,
		0.2,
		to_units(bottom - top) + BACKING_INSET)

	var node := MeshInstance3D.new()
	node.name = "Backing"
	node.mesh = mesh
	node.material_override = _material(BACKING_COLOR, 0.0, 0.95)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.position = to_world(
		_course_width * 0.5, (top + bottom) * 0.5, -FLOOR_DROP - 0.1)
	add_child(node)


func _build_pieces() -> void:
	## Course geometry, rebuilt from the replay and nothing else.
	##
	## The viewer does not know how this course was generated and must not:
	## the replay gives it every box and every circle with a role attached,
	## and a course it has never heard of draws correctly for free.
	var pieces: Array = _course.get("pieces", [])
	if pieces.is_empty():
		return

	var root := Node3D.new()
	root.name = "Course"
	add_child(root)

	for raw in pieces:
		var spec: Dictionary = raw
		var role := str(spec.get("role", "ramp"))
		var node := MeshInstance3D.new()
		node.name = "Piece%d" % int(spec.get("id", 0))

		if str(spec.get("type", "")) == "circle":
			var radius := to_units(float(spec.get("radius", 0.0)))
			var post := CylinderMesh.new()
			post.top_radius = radius
			post.bottom_radius = radius
			post.height = PEG_HEIGHT
			post.radial_segments = 24
			node.mesh = post
			node.position = to_world(
				float(spec.get("x", 0.0)), float(spec.get("y", 0.0)),
				PEG_HEIGHT * 0.5)
		else:
			var slab := BoxMesh.new()
			slab.size = Vector3(
				to_units(float(spec.get("width", 0.0))),
				PIECE_HEIGHT,
				to_units(float(spec.get("height", 0.0))))
			node.mesh = slab
			node.position = to_world(
				float(spec.get("x", 0.0)), float(spec.get("y", 0.0)),
				PIECE_HEIGHT * 0.5)
			# Simulation y becomes world Z, which mirrors the plane, so a
			# rotation that turns one way in simulation coordinates turns the
			# other way here. Negating it is what puts a ramp where the
			# replay says it is.
			node.rotation_degrees = Vector3(
				0.0, -float(spec.get("rotation_degrees", 0.0)), 0.0)

		node.material_override = _piece_material(role, str(spec.get("material", "")))
		root.add_child(node)
		if role == "gate":
			_gate_nodes.append(node)


func _piece_material(role: String, material: String) -> StandardMaterial3D:
	match role:
		"wall":
			return _material(WALL_COLOR, 0.05, 0.80)
		"peg":
			return _emissive(PEG_COLOR, ACCENT_EMISSION, 0.55)
		"gate":
			return _emissive(GATE_COLOR, ACCENT_EMISSION, 0.62)
		"jump_pad":
			return _emissive(PAD_COLOR, ACCENT_EMISSION, 0.55)
	# An ordinary surface. Slick reads lighter than grippy, which is the one
	# distinction a viewer can actually use: it says where a racer will slide.
	if material == "slick":
		return _material(RAMP_SLICK_COLOR, 0.20, 0.35)
	return _material(RAMP_COLOR, 0.05, 0.70)


func _build_spinners() -> void:
	## A hub and its arms on one pivot, exactly as the simulation builds them.
	##
	## The arms are placed at their rest angles and never touched again: every
	## frame writes one rotation into the pivot, taken from what the
	## simulation actually did. Nothing here integrates an angular speed, so
	## playback cannot drift away from the race it is showing.
	var spinners: Array = _course.get("spinners", [])
	if spinners.is_empty():
		return

	var root := Node3D.new()
	root.name = "Spinners"
	add_child(root)

	var arm_material := _emissive(SPINNER_COLOR, ACCENT_EMISSION, 0.45)
	var hub_material := _material(SPINNER_HUB_COLOR, 0.15, 0.55)

	for raw in spinners:
		var spec: Dictionary = raw
		var pivot := Node3D.new()
		pivot.name = "Spinner%d" % int(spec.get("id", 0))
		pivot.position = to_world(
			float(spec.get("x", 0.0)), float(spec.get("y", 0.0)), 0.0)
		root.add_child(pivot)

		var hub_radius := to_units(float(spec.get("hub_radius", 0.0)))
		var hub := CylinderMesh.new()
		hub.top_radius = hub_radius
		hub.bottom_radius = hub_radius
		hub.height = SPINNER_HUB_HEIGHT
		hub.radial_segments = 24
		var hub_node := MeshInstance3D.new()
		hub_node.name = "Hub"
		hub_node.mesh = hub
		hub_node.material_override = hub_material
		hub_node.position = Vector3(0.0, SPINNER_HUB_HEIGHT * 0.5, 0.0)
		pivot.add_child(hub_node)

		var arm_count := maxi(1, int(spec.get("arm_count", 1)))
		var arm_length := to_units(float(spec.get("arm_length", 0.0)))
		var arm_thickness := to_units(float(spec.get("arm_thickness", 0.0)))
		var distance := hub_radius + arm_length * 0.5
		var step := 360.0 / float(arm_count)

		for index in arm_count:
			# The rest angle in *simulation* degrees. The same mirror applies
			# to a child's placement as to the pivot's rotation, so the offset
			# is computed with simulation trigonometry and the box is then
			# turned by the negated angle to lie along it.
			var angle := deg_to_rad(float(index) * step)
			var arm := BoxMesh.new()
			arm.size = Vector3(arm_length, SPINNER_ARM_HEIGHT, arm_thickness)
			var arm_node := MeshInstance3D.new()
			arm_node.name = "Arm%d" % index
			arm_node.mesh = arm
			arm_node.material_override = arm_material
			arm_node.position = Vector3(
				distance * cos(angle),
				SPINNER_ARM_HEIGHT * 0.5,
				distance * sin(angle))
			arm_node.rotation_degrees = Vector3(0.0, -float(index) * step, 0.0)
			pivot.add_child(arm_node)

		_spinner_pivots[int(spec.get("id", 0))] = pivot


func _build_finish_line() -> void:
	## One lit bar across the finish plane. The only piece of chrome the
	## course itself does not carry, and the only one worth adding: a viewer
	## has to be able to see where the race ends.
	var finish: Dictionary = _course.get("finish", {})
	if finish.is_empty():
		return
	var mesh := BoxMesh.new()
	mesh.size = Vector3(
		to_units(_course_width), FINISH_BAR_HEIGHT, FINISH_BAR_THICKNESS)

	var node := MeshInstance3D.new()
	node.name = "FinishLine"
	node.mesh = mesh
	node.material_override = _emissive(FINISH_COLOR, FINISH_EMISSION, 0.15)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.position = to_world(
		_course_width * 0.5, float(finish.get("y", 0.0)), FINISH_BAR_HEIGHT * 0.5)
	add_child(node)


func _build_racers() -> void:
	for meta in _racer_meta:
		var radius := to_units(float(meta.get("radius", 30.0)))
		var color := _color_of(meta)

		var mesh := SphereMesh.new()
		mesh.radius = radius
		mesh.height = radius * 2.0
		mesh.radial_segments = 32
		mesh.rings = 16

		var live := _material(color, 0.10, 0.32)
		live.emission_enabled = true
		live.emission = color
		live.emission_energy_multiplier = 0.35
		var done := _material(color.darkened(FINISHED_DIM), 0.05, 0.70)

		var node := MeshInstance3D.new()
		node.name = "Racer%d" % int(meta.get("id", 0))
		node.mesh = mesh
		node.material_override = live
		add_child(node)

		_racer_nodes.append(node)
		_racer_live.append(live)
		_racer_done.append(done)
		_racer_radius.append(radius)


func _build_hud() -> void:
	_hud = RaceHud.new()
	_hud.name = "RaceHUD"
	add_child(_hud)
	_hud.configure(_replay)


# --- playback ------------------------------------------------------------

func _update_camera(frame: Dictionary, next_frame: Dictionary, blend: float) -> void:
	## Follow the track the replay recorded. No follow logic lives here.
	var top := lerpf(
		float(frame.get("camera_y", 0.0)),
		float(next_frame.get("camera_y", 0.0)),
		blend)
	_camera.position = Vector3(
		0.0, CAMERA_HEIGHT, to_units(top + VIEW_HEIGHT * 0.5))


func _update_racers(current: Array, upcoming: Array, blend: float) -> void:
	for index in _racer_nodes.size():
		if index >= current.size():
			continue
		var now: Dictionary = current[index]
		var soon: Dictionary = upcoming[index] if index < upcoming.size() else now
		var node := _racer_nodes[index]

		# A retired racer was taken out of the simulation's space, so it is
		# taken out of the picture too rather than left lying on the course.
		if bool(now.get("retired", false)):
			node.visible = false
			continue
		node.visible = true

		# Interpolation is cosmetic: the replay data is never modified.
		var x := lerpf(float(now.get("x", 0.0)), float(soon.get("x", 0.0)), blend)
		var y := lerpf(float(now.get("y", 0.0)), float(soon.get("y", 0.0)), blend)
		var spin := lerp_angle(
			deg_to_rad(float(now.get("rotation_degrees", 0.0))),
			deg_to_rad(float(soon.get("rotation_degrees", 0.0))),
			blend)

		node.position = to_world(x, y, _racer_radius[index])
		# A racer rolls about the axis out of the simulation plane, which is
		# world Y, and the plane is mirrored - so the angle is negated here
		# exactly as a ramp's is.
		node.rotation.y = -spin
		node.material_override = (
			_racer_done[index] if bool(now.get("finished", false))
			else _racer_live[index])


func _update_spinners(current: Array, upcoming: Array, blend: float) -> void:
	## Move the spinners purely from what the replay recorded.
	##
	## No motion is computed here: the viewer never reads angular speed or
	## start angle, only the transform Python actually had. The angle is
	## blended the short way round so an arm crossing 359 to 1 degree keeps
	## turning forwards instead of unwinding almost a full circle.
	if _spinner_pivots.is_empty():
		return

	var next_by_id := {}
	for raw in upcoming:
		var soon: Dictionary = raw
		next_by_id[int(soon.get("id", -1))] = soon

	for raw in current:
		var now: Dictionary = raw
		var id := int(now.get("id", -1))
		var pivot: Node3D = _spinner_pivots.get(id)
		if pivot == null:
			continue

		var x := float(now.get("x", 0.0))
		var y := float(now.get("y", 0.0))
		var angle := deg_to_rad(float(now.get("rotation_degrees", 0.0)))
		if next_by_id.has(id):
			var soon: Dictionary = next_by_id[id]
			x = lerpf(x, float(soon.get("x", x)), blend)
			y = lerpf(y, float(soon.get("y", y)), blend)
			angle = lerp_angle(
				angle, deg_to_rad(float(soon.get("rotation_degrees", 0.0))), blend)

		pivot.position = to_world(x, y, 0.0)
		pivot.rotation.y = -angle


func _update_gates(frame: Dictionary) -> void:
	## The gate is removed from the simulation, not moved, so it is a state
	## rather than a transform: the frame says whether it is still there.
	var open := bool(frame.get("gates_open", false))
	if open == _gates_hidden:
		return
	_gates_hidden = open
	for node in _gate_nodes:
		node.visible = not open


# --- small builders -------------------------------------------------------

func _material(color: Color, metallic: float, roughness: float) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = metallic
	material.metallic_specular = 0.35
	material.roughness = roughness
	return material


func _emissive(color: Color, energy: float, roughness: float) -> StandardMaterial3D:
	var material := _material(color, 0.0, roughness)
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
